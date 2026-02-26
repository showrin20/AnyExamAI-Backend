"""
Pydantic schemas for IELTS Listening test.
These schemas match the listening JSON schema v2.1 used by the frontend.
Audio blocks follow the fixed IELTS computer-based 8-block structure.
"""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


# ── Voice / accent constants ──────────────────────────────────────────

VOICES: Dict[str, str] = {
    "uk": "en-GB-SoniaNeural",
    "us": "en-US-JennyNeural",
    "au": "en-AU-NatashaNeural",
    "nz": "en-NZ-MollyNeural",
    "ca": "en-CA-ClaraNeural",
}

VOICE_RATE: str = "-5%"

# ── Fixed IELTS computer-based audio block ranges ────────────────────

AUDIO_BLOCK_RANGES: List[Dict[str, Any]] = [
    {"block": 1, "section": 1, "q_start": 1,  "q_end": 4},
    {"block": 2, "section": 1, "q_start": 5,  "q_end": 10},
    {"block": 3, "section": 2, "q_start": 11, "q_end": 16},
    {"block": 4, "section": 2, "q_start": 17, "q_end": 20},
    {"block": 5, "section": 3, "q_start": 21, "q_end": 24},
    {"block": 6, "section": 3, "q_start": 25, "q_end": 30},
    {"block": 7, "section": 4, "q_start": 31, "q_end": 35},
    {"block": 8, "section": 4, "q_start": 36, "q_end": 40},
]


# ── Answer constraints ───────────────────────────────────────────────

class AnswerConstraints(BaseModel):
    instruction_text: str
    max_words: int = Field(..., ge=1, le=6)
    allow_number: bool = True
    case_sensitive: bool = False
    hyphen_counts_as_one: bool = True


# ── Option item (for MCQ / matching) ─────────────────────────────────

class OptionItem(BaseModel):
    label: str = Field(..., pattern=r"^[A-Z]$")
    text: str


# ── Speaker ──────────────────────────────────────────────────────────

class Speaker(BaseModel):
    name: str
    role: str
    accent: str


class Speakers(BaseModel):
    count: int = Field(..., ge=1, le=4)
    details: List[Speaker] = Field(..., min_length=1, max_length=4)


# ── Section context ──────────────────────────────────────────────────

class SectionContext(BaseModel):
    setting: str
    purpose: str
    description: str


# ── Audio asset per accent ───────────────────────────────────────────

class AudioAsset(BaseModel):
    voice: str
    rate: str = VOICE_RATE
    file: str
    status: Literal["pending", "generated", "failed"] = "pending"


# ── Question range ───────────────────────────────────────────────────

class QuestionRange(BaseModel):
    min: int = Field(..., ge=1, le=40)
    max: int = Field(..., ge=1, le=40)


# ── Audio block (the 8-block structure) ──────────────────────────────

class AudioBlock(BaseModel):
    """One of the 8 fixed audio blocks for IELTS computer-based listening."""
    block_number: int = Field(..., ge=1, le=8)
    section_number: int = Field(..., ge=1, le=4)
    question_range: QuestionRange
    questions: List[Dict[str, Any]]
    transcript_chunk: str
    audio_assets: Dict[str, AudioAsset] = {}


# ── Section (from Gemini – raw) ──────────────────────────────────────

class ListeningSection(BaseModel):
    section_number: int = Field(..., ge=1, le=4)
    section_type: Literal[
        "social_dialogue", "social_monologue",
        "academic_discussion", "academic_lecture",
    ]
    section_instructions: str
    context: SectionContext
    speakers: Speakers
    difficulty_band: str
    audio_duration_seconds: int = Field(..., ge=180, le=720)
    audio_transcript: str = Field(..., min_length=500)
    section_question_range: QuestionRange
    questions: List[Dict[str, Any]]
    skills_assessed: Optional[List[str]] = None


# ── Test metadata ────────────────────────────────────────────────────

class ListeningTestMetadata(BaseModel):
    schema_version: str = "2.1"
    generated_at: str
    difficulty_band: str = Field(
        ...,
        pattern=r"^(5\.0|5\.5|6\.0|6\.5|7\.0|7\.5|8\.0|8\.5|9\.0)$",
    )
    delivery_format: Literal["paper-based", "computer-based"] = "computer-based"
    test_source: Optional[str] = None
    audio_characteristics: Optional[Dict[str, Any]] = None


# ── Playback rules ───────────────────────────────────────────────────

class PlaybackRules(BaseModel):
    play_once_only: bool = True
    no_rewind: bool = True
    no_pause_during_section: bool = True
    notes_allowed: bool = True


# ── Timing defaults ──────────────────────────────────────────────────

class TimingDefaults(BaseModel):
    pre_read_seconds: int = Field(30, ge=10, le=60)
    end_section_check_seconds: int = Field(30, ge=10, le=60)
    between_sections_pause_seconds: int = Field(30, ge=5, le=60)


class TestFlow(BaseModel):
    section_sequence: List[int] = [1, 2, 3, 4]
    timing_defaults: TimingDefaults = TimingDefaults()
    global_instructions: Optional[str] = None


# ── Complete listening test (final response) ─────────────────────────

class IELTSListeningTest(BaseModel):
    """Complete IELTS Listening test with 8 audio blocks."""
    test_id: str
    test_type: Literal[
        "IELTS Academic Listening",
        "IELTS General Training Listening",
    ]
    total_questions: int = 40
    audio_duration_minutes: int = Field(..., ge=28, le=35)
    transfer_time_minutes: int = 0
    test_metadata: ListeningTestMetadata
    playback_rules: PlaybackRules
    test_flow: TestFlow
    sections: List[ListeningSection] = Field(..., min_length=4, max_length=4)
    audio_blocks: List[AudioBlock] = Field(..., min_length=8, max_length=8)
    answer_key: Dict[str, Union[str, int, List[str]]]
