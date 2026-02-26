"""
IELTS Listening Test Generation Service.

Pipeline:
1.  Call Gemini to produce 4 sections / 40 questions + long transcripts.
2.  Split each section transcript into two halves (heuristic), producing
    exactly **8 audio blocks** that follow the fixed IELTS computer-based
    question ranges.
3.  Render each block × each accent as an MP3 via edge-tts.
4.  Validate, build answer_key, and return the final JSON.
"""

import asyncio
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import edge_tts

from core.gemini_client import GeminiClient, get_gemini_client
from core.exceptions import GeminiAPIError, SchemaValidationError
from services.base import BaseIELTSService
from schemas.listening import (
    AUDIO_BLOCK_RANGES,
    VOICES,
    VOICE_RATE,
)

# ── Logger ────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ── Constants ─────────────────────────────────────────────────────────
MIN_TRANSCRIPT_LENGTH = 500
MAX_RETRIES = 3
RETRY_DELAY_SECONDS = 2


# =====================================================================
# Service
# =====================================================================
class ListeningTestService(BaseIELTSService):
    """Service for generating IELTS Listening tests using Gemini + edge-tts."""

    VALID_BANDS = [
        "5.0", "5.5", "6.0", "6.5", "7.0", "7.5", "8.0", "8.5", "9.0"
    ]

    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        self.gemini_client = gemini_client or get_gemini_client()
        logger.info("ListeningTestService initialized")

    # ─────────────────────────────────────────────────────────────────
    # Schema validation (lightweight – mirrors reading_service pattern)
    # ─────────────────────────────────────────────────────────────────
    def validate_schema(self, data: Dict[str, Any]) -> bool:  # noqa: C901
        errors: List[str] = []

        # Top-level keys
        for key in (
            "test_type", "sections", "total_questions",
            "audio_duration_minutes", "test_metadata",
        ):
            if key not in data:
                errors.append(f"Missing required key: {key}")

        if data.get("total_questions") != 40:
            errors.append(
                f"total_questions must be 40, got {data.get('total_questions')}"
            )

        # Sections
        sections = data.get("sections", [])
        if len(sections) != 4:
            errors.append(f"Must have exactly 4 sections, got {len(sections)}")

        total_q = 0
        for idx, sec in enumerate(sections, 1):
            for k in (
                "section_number", "section_type", "audio_transcript",
                "questions", "section_question_range", "section_instructions",
                "context", "speakers", "difficulty_band", "audio_duration_seconds",
            ):
                if k not in sec:
                    errors.append(f"Section {idx} missing key: {k}")

            qs = sec.get("questions", [])
            if len(qs) != 10:
                errors.append(
                    f"Section {idx} must have 10 questions, got {len(qs)}"
                )
            total_q += len(qs)

            transcript = sec.get("audio_transcript", "")
            if len(transcript) < MIN_TRANSCRIPT_LENGTH:
                errors.append(
                    f"Section {idx} transcript too short "
                    f"({len(transcript)} chars, minimum {MIN_TRANSCRIPT_LENGTH})"
                )

        if total_q != 40:
            errors.append(f"Total questions across sections: {total_q}, expected 40")

        # Metadata
        meta = data.get("test_metadata", {})
        if meta.get("schema_version") != "2.1":
            errors.append(f"Wrong schema_version: {meta.get('schema_version')}")
        if meta.get("difficulty_band") not in self.VALID_BANDS:
            errors.append(f"Invalid difficulty_band: {meta.get('difficulty_band')}")

        if errors:
            logger.error(f"Validation failed ({len(errors)} errors): {errors}")
            raise SchemaValidationError(
                message="Schema validation failed",
                details={"errors": errors},
            )

        logger.info("Schema validation passed")
        return True

    # ─────────────────────────────────────────────────────────────────
    # Gemini prompt
    # ─────────────────────────────────────────────────────────────────
    def _build_prompt(self, test_id: str, difficulty: str) -> str:
        return f'''You are an IELTS test content generator. Generate a COMPLETE IELTS Listening Test JSON.

CRITICAL REQUIREMENTS:
1. Output ONLY valid JSON - NO markdown, NO code blocks, NO explanations
2. The JSON must be parseable directly by json.loads()

TEST STRUCTURE:
- test_id: "{test_id}"
- test_type: "IELTS Academic Listening"
- total_questions: 40 (exactly)
- audio_duration_minutes: 30
- transfer_time_minutes: 0 (computer-based)
- 4 sections with 10 questions each

SECTION REQUIREMENTS:
Section 1 (Questions 1-10): social_dialogue - Two people in everyday social context (easiest)
Section 2 (Questions 11-20): social_monologue - One speaker on social topic  
Section 3 (Questions 21-30): academic_discussion - 2-4 people in academic setting
Section 4 (Questions 31-40): academic_lecture - One speaker on academic topic (hardest)

TARGET DIFFICULTY: {difficulty}

FOR EACH SECTION, include:
- section_number: 1, 2, 3, or 4
- section_type: appropriate type
- section_instructions: IELTS-style instructions
- context: {{setting, purpose, description}}
- speakers: {{count, details: [{{name, role, accent}}]}}
- difficulty_band: progressive ("5.5" for S1, "6.0" for S2, "6.5" for S3, "7.0" for S4)
- audio_duration_seconds: 420-600
- audio_transcript: FULL natural dialogue/monologue (minimum 600 words per section)
- section_question_range: {{min, max}}
- questions: exactly 10 questions with proper IELTS question types

NOTE: Do NOT include audio_assets – audio files will be generated separately.

=== QUESTION FORMAT (CRITICAL - FOLLOW EXACTLY) ===

For form_completion and note_completion questions, use this EXACT format:

1. "form_context" / "note_context": The TITLE of the notes section
2. "subheading": Optional category/subsection
3. "form_field" / "note_topic": The SENTENCE with a ______ placeholder where the answer goes.
   IMPORTANT: Use exactly 6 underscores (______) to mark where the blank/answer goes.

QUESTION TYPES TO USE:
- form_completion: For Section 1 (booking forms, applications, registrations)
- note_completion: For Section 2 and 4 (information notes, lecture notes)
- multiple_choice: For Section 3 (with question_text, options array with {{label, text}} objects, select_count: 1)
- sentence_completion: For any section (incomplete_sentence with ______ placeholder)
- matching: For Section 3 (item_to_match, items_to_match array, options array with {{label, text}} objects, matching_type)
- table_completion: For any section (table_title, table_context, cell_location)

EACH QUESTION MUST HAVE:
- question_number: 1-40 (continuous across sections)
- type: one of the types above
- answer: the correct answer (just the word/number, not the full sentence)
- alternative_answers: [] (acceptable spelling variations)
- answer_constraints: {{instruction_text, max_words, allow_number: true, case_sensitive: false, hyphen_counts_as_one: true}}
- max_word_count: 1, 2, or 3 depending on instruction
- explanation: brief explanation of correct answer

TRANSCRIPT REQUIREMENTS:
- Section 1: Casual conversation (booking, inquiry, complaint)
- Section 2: Information presentation (tour guide, orientation, instructions)
- Section 3: Academic discussion (students and tutor discussing assignment)
- Section 4: Academic lecture (university-level topic)
- Include speaker labels like "RECEPTIONIST:", "STUDENT:", "PROFESSOR:"
- Make transcripts natural with hesitations, corrections, filler words
- Answers must appear naturally in the transcript

RETURN FORMAT (keys at top level):
{{
  "test_id": "{test_id}",
  "test_type": "IELTS Academic Listening",
  "total_questions": 40,
  "audio_duration_minutes": 30,
  "transfer_time_minutes": 0,
  "test_metadata": {{
    "schema_version": "2.1",
    "generated_at": "{datetime.now(timezone.utc).isoformat()}",
    "difficulty_band": "{difficulty}",
    "delivery_format": "computer-based",
    "test_source": "AI Generated Practice Test",
    "audio_characteristics": {{
      "accents": ["British", "American", "Australian", "New Zealand", "Canadian"],
      "speech_rate": "moderate",
      "background_noise": false
    }}
  }},
  "playback_rules": {{
    "play_once_only": true,
    "no_rewind": true,
    "no_pause_during_section": true,
    "notes_allowed": true
  }},
  "test_flow": {{
    "section_sequence": [1, 2, 3, 4],
    "timing_defaults": {{
      "pre_read_seconds": 30,
      "end_section_check_seconds": 30,
      "between_sections_pause_seconds": 30
    }},
    "global_instructions": "You will hear four recordings. Answer the questions as you listen."
  }},
  "sections": [ ... 4 section objects ... ]
}}

OUTPUT THE COMPLETE JSON NOW:'''

    # ─────────────────────────────────────────────────────────────────
    # Transcript splitting heuristic
    # ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _split_transcript(transcript: str, ratio: float = 0.5) -> Tuple[str, str]:
        """
        Split a transcript roughly at *ratio* of its lines, preferring a
        break at a speaker label boundary so each chunk starts with a
        speaker tag (e.g. ``STUDENT:``).
        """
        lines = transcript.strip().split("\n")
        target = int(len(lines) * ratio)

        # Try to find a speaker-label line near the target
        speaker_re = re.compile(r"^[A-Z][A-Z\s\.\-']+:")
        best = target
        for offset in range(0, len(lines) // 4):
            for candidate in (target + offset, target - offset):
                if 0 < candidate < len(lines) and speaker_re.match(lines[candidate]):
                    best = candidate
                    break
            else:
                continue
            break

        part_a = "\n".join(lines[:best]).strip()
        part_b = "\n".join(lines[best:]).strip()
        # Fallback: if either part is empty, just hard-split
        if not part_a or not part_b:
            mid = len(transcript) // 2
            part_a = transcript[:mid].strip()
            part_b = transcript[mid:].strip()
        return part_a, part_b

    # ─────────────────────────────────────────────────────────────────
    # Build the 8 audio blocks from sections + questions
    # ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _build_audio_blocks(
        sections: List[Dict[str, Any]],
    ) -> List[Dict[str, Any]]:
        """
        Build exactly 8 audio blocks.

        Each section is split into two transcript halves; questions are
        assigned to the block whose range they fall into (keyed by
        ``question_number``).
        """
        # Index questions by question_number across all sections
        q_by_num: Dict[int, Dict[str, Any]] = {}
        for sec in sections:
            for q in sec.get("questions", []):
                q_by_num[q["question_number"]] = q

        # Build section-number → transcript halves mapping
        section_halves: Dict[int, Tuple[str, str]] = {}
        for sec in sections:
            sn = sec["section_number"]
            transcript = sec.get("audio_transcript", "")
            section_halves[sn] = ListeningTestService._split_transcript(transcript)

        blocks: List[Dict[str, Any]] = []
        for bdef in AUDIO_BLOCK_RANGES:
            block_num = bdef["block"]
            sec_num = bdef["section"]
            q_start = bdef["q_start"]
            q_end = bdef["q_end"]

            # Determine which half of the section transcript this block uses.
            # Blocks 1, 3, 5, 7 → first half; 2, 4, 6, 8 → second half
            half_idx = 0 if block_num % 2 == 1 else 1
            transcript_chunk = section_halves.get(sec_num, ("", ""))[half_idx]

            # Collect questions whose question_number is in [q_start, q_end]
            block_questions = [
                q_by_num[n]
                for n in range(q_start, q_end + 1)
                if n in q_by_num
            ]

            blocks.append({
                "block_number": block_num,
                "section_number": sec_num,
                "question_range": {"min": q_start, "max": q_end},
                "questions": block_questions,
                "transcript_chunk": transcript_chunk,
                "audio_assets": {},   # filled later by audio renderer
            })

        return blocks

    # ─────────────────────────────────────────────────────────────────
    # edge-tts rendering for a single block + accent
    # ─────────────────────────────────────────────────────────────────
    @staticmethod
    async def _render_one(
        transcript: str, voice: str, rate: str, output_path: str,
    ) -> Tuple[bool, str]:
        try:
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)
            communicate = edge_tts.Communicate(transcript, voice, rate=rate)
            await communicate.save(output_path)
            return True, "generated"
        except Exception as exc:
            logger.error(f"Audio render failed ({output_path}): {exc}")
            return False, f"failed: {exc}"

    # ─────────────────────────────────────────────────────────────────
    # Render all audio blocks
    # ─────────────────────────────────────────────────────────────────
    async def _render_audio_blocks(
        self,
        blocks: List[Dict[str, Any]],
        test_id: str,
        output_dir: str,
    ) -> List[Dict[str, Any]]:
        """Generate MP3 files for every block × accent combination."""
        tasks: List[asyncio.Task] = []
        task_meta: List[Tuple[int, str]] = []  # (block_idx, accent)

        for idx, block in enumerate(blocks):
            bn = block["block_number"]
            chunk = block.get("transcript_chunk", "")
            if not chunk:
                logger.warning(f"Block {bn} has empty transcript chunk – skipping audio")
                continue

            for accent, voice in VOICES.items():
                rel_path = f"audio/listening/{test_id}/block{bn}/{accent}.mp3"
                abs_path = os.path.join(output_dir, rel_path)

                block["audio_assets"][accent] = {
                    "voice": voice,
                    "rate": VOICE_RATE,
                    "file": rel_path,
                    "status": "pending",
                }

                tasks.append(
                    self._render_one(chunk, voice, VOICE_RATE, abs_path)
                )
                task_meta.append((idx, accent))

        if tasks:
            logger.info(f"Rendering {len(tasks)} audio files …")
            results = await asyncio.gather(*tasks, return_exceptions=True)

            for (bidx, accent), result in zip(task_meta, results):
                if isinstance(result, Exception):
                    blocks[bidx]["audio_assets"][accent]["status"] = (
                        f"failed: {result}"
                    )
                else:
                    _ok, status = result
                    blocks[bidx]["audio_assets"][accent]["status"] = status

        return blocks

    # ─────────────────────────────────────────────────────────────────
    # Fix-ups applied to raw Gemini output
    # ─────────────────────────────────────────────────────────────────
    def _fix_common_issues(self, data: Dict[str, Any], test_id: str) -> Dict[str, Any]:
        data["test_id"] = test_id

        # Metadata defaults
        meta = data.setdefault("test_metadata", {})
        meta.setdefault("schema_version", "2.1")
        meta.setdefault("generated_at", datetime.now(timezone.utc).isoformat())
        meta.setdefault("delivery_format", "computer-based")
        meta.setdefault("difficulty_band", "6.5")

        # Playback rules
        data.setdefault("playback_rules", {
            "play_once_only": True,
            "no_rewind": True,
            "no_pause_during_section": True,
            "notes_allowed": True,
        })

        # Test flow
        data.setdefault("test_flow", {
            "section_sequence": [1, 2, 3, 4],
            "timing_defaults": {
                "pre_read_seconds": 30,
                "end_section_check_seconds": 30,
                "between_sections_pause_seconds": 30,
            },
        })

        return data

    # ─────────────────────────────────────────────────────────────────
    # Build the answer key from questions
    # ─────────────────────────────────────────────────────────────────
    @staticmethod
    def _build_answer_key(sections: List[Dict[str, Any]]) -> Dict[str, Any]:
        key: Dict[str, Any] = {}
        for sec in sections:
            for q in sec.get("questions", []):
                qn = str(q.get("question_number"))
                answer = q.get("answer")
                alts = q.get("alternative_answers", [])
                if alts:
                    key[qn] = (
                        [answer] + alts if isinstance(answer, str) else answer
                    )
                else:
                    key[qn] = answer
        return key

    # ─────────────────────────────────────────────────────────────────
    # Main entry point
    # ─────────────────────────────────────────────────────────────────
    async def generate_test(
        self,
        difficulty: str = "6.5",
        output_dir: str = "data/generated/listening",
    ) -> Dict[str, Any]:
        """
        Full pipeline:
        1. Generate test JSON via Gemini.
        2. Build 8 audio blocks.
        3. Render audio.
        4. Validate & return.
        """
        if difficulty not in self.VALID_BANDS:
            raise SchemaValidationError(
                message=f"Invalid difficulty band: {difficulty}",
                details={"valid_bands": self.VALID_BANDS},
            )

        test_id = uuid.uuid4().hex[:8]
        last_error: Optional[Exception] = None
        all_errors: List[str] = []

        for attempt in range(1, MAX_RETRIES + 1):
            try:
                logger.info(
                    f"Generating listening test (attempt {attempt}/{MAX_RETRIES})"
                )

                # 1 ── Gemini call ────────────────────────────────────
                prompt = self._build_prompt(test_id, difficulty)
                response_text = await self.gemini_client.generate_content(prompt)
                test_data = self.extract_json_from_response(response_text)

                # 2 ── Fix-ups ────────────────────────────────────────
                test_data = self._fix_common_issues(test_data, test_id)

                # 3 ── Validate core structure ────────────────────────
                self.validate_schema(test_data)

                # 4 ── Build 8 audio blocks ───────────────────────────
                sections = test_data.get("sections", [])
                blocks = self._build_audio_blocks(sections)
                logger.info(f"Built {len(blocks)} audio blocks")

                # 5 ── Render MP3s ────────────────────────────────────
                blocks = await self._render_audio_blocks(
                    blocks, test_id, output_dir,
                )

                test_data["audio_blocks"] = blocks

                # 6 ── Answer key ─────────────────────────────────────
                test_data["answer_key"] = self._build_answer_key(sections)

                logger.info(
                    f"Listening test {test_id} generated on attempt {attempt}"
                )
                return test_data

            except SchemaValidationError as exc:
                last_error = exc
                all_errors.append(
                    f"Attempt {attempt}: {exc.details.get('errors', [])}"
                )
                logger.warning(
                    f"Validation failed on attempt {attempt}: {exc.details}"
                )
            except Exception as exc:
                last_error = exc
                all_errors.append(f"Attempt {attempt}: {exc}")
                logger.error(
                    f"Error on attempt {attempt}: {exc}", exc_info=True
                )

            if attempt < MAX_RETRIES:
                logger.info(f"Retrying in {RETRY_DELAY_SECONDS}s …")
                await asyncio.sleep(RETRY_DELAY_SECONDS)

        # Exhausted retries
        logger.error(f"All {MAX_RETRIES} attempts failed: {all_errors}")
        if isinstance(last_error, SchemaValidationError):
            raise SchemaValidationError(
                message=f"Validation failed after {MAX_RETRIES} attempts",
                details={
                    "all_errors": all_errors,
                    "last_errors": last_error.details.get("errors", []),
                },
            )
        raise last_error  # type: ignore[misc]


# ── Dependency injection ─────────────────────────────────────────────
def get_listening_service() -> ListeningTestService:
    return ListeningTestService()
