"""
IELTS Speaking Test Service - Core logic for the AI-powered speaking examiner.

Uses Gemini for chat, transcription (ASR), and text-to-speech (TTS).
"""

import logging
import os
import re
import tempfile
import time
import wave

from google import genai
from google.genai import types
from google.genai.errors import ServerError

from core.config import get_settings

logger = logging.getLogger(__name__)

# --- Config ---
CHAT_MODEL = "gemini-2.5-flash"
TTS_MODEL = "gemini-2.5-flash-preview-tts"
TTS_VOICE = "Sadaltager"

SYSTEM_INSTRUCTION = """You are a professional IELTS Speaking Test examiner. Conduct a realistic mock speaking test.

## Test Structure:
- **Part 1** (4-5 questions): Introduction and familiar topic questions (home, work, studies, hobbies).
- **Part 2**: Present a cue card topic with bullet points. Tell the candidate to prepare for 1 minute then speak for 1-2 minutes. After they speak, ask 1-2 brief follow-ups.
- **Part 3** (3-4 questions): Abstract discussion questions related to the Part 2 topic.

## Rules:
- Ask ONE question at a time. Wait for the candidate's response before continuing.
- Be professional, warm, and encouraging.
- Transition between parts naturally with clear announcements.
- Keep responses concise — you are an examiner, not lecturing.
- After Part 3, provide detailed feedback with estimated band scores:
  - Fluency and Coherence (band + brief comment)
  - Lexical Resource (band + brief comment)
  - Grammatical Range and Accuracy (band + brief comment)
  - Pronunciation (band + brief comment based on word choice and phrasing)
  - Overall Band Score
  - 2-3 specific tips for improvement

When you receive "START_TEST", greet the candidate warmly and begin Part 1."""


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    """Return a shared Gemini client (singleton) so the underlying HTTP
    connection is reused across calls and never prematurely closed."""
    global _client
    if _client is None:
        settings = get_settings()
        _client = genai.Client(api_key=settings.gemini_api_key)
    return _client


def clean_for_tts(text: str) -> str:
    """Strip markdown so TTS reads cleanly."""
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text)
    text = re.sub(r"\*(.*?)\*", r"\1", text)
    text = re.sub(r"#{1,6}\s*", "", text)
    text = re.sub(r"[-*•]\s", "", text)
    return text.strip()


def text_to_speech(client: genai.Client, text: str, max_retries: int = 3) -> str:
    """Generate speech audio from text using Gemini TTS (with retry)."""
    clean_text = clean_for_tts(text)

    for attempt in range(1, max_retries + 1):
        try:
            response = client.models.generate_content(
                model=TTS_MODEL,
                contents=clean_text,
                config=types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=types.SpeechConfig(
                        voice_config=types.VoiceConfig(
                            prebuilt_voice_config=types.PrebuiltVoiceConfig(
                                voice_name=TTS_VOICE,
                            )
                        )
                    ),
                ),
            )
            audio_data = response.candidates[0].content.parts[0].inline_data.data

            tmp = tempfile.NamedTemporaryFile(suffix=".wav", delete=False)
            with wave.open(tmp.name, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(24000)
                wf.writeframes(audio_data)
            return tmp.name
        except ServerError as e:
            if attempt < max_retries:
                wait = 2 ** attempt
                logger.warning(f"[TTS] Server error (attempt {attempt}/{max_retries}), retrying in {wait}s… {e}")
                time.sleep(wait)
            else:
                logger.error(f"[TTS] All {max_retries} attempts failed: {e}")
                raise


def transcribe(client: genai.Client, audio_path: str) -> str:
    """Transcribe audio to text using Gemini's multimodal input."""
    with open(audio_path, "rb") as f:
        audio_bytes = f.read()

    ext = os.path.splitext(audio_path)[1].lower()
    mime_map = {
        ".wav": "audio/wav",
        ".mp3": "audio/mp3",
        ".ogg": "audio/ogg",
        ".webm": "audio/webm",
        ".m4a": "audio/mp4",
    }
    mime_type = mime_map.get(ext, "audio/wav")

    response = client.models.generate_content(
        model=CHAT_MODEL,
        contents=[
            types.Part.from_bytes(data=audio_bytes, mime_type=mime_type),
            "Transcribe this audio exactly as spoken. Output ONLY the transcription, nothing else.",
        ],
    )
    if response.text is None:
        logger.warning("[Transcribe] Gemini returned no text for audio: %s", audio_path)
        return ""
    return response.text.strip()
