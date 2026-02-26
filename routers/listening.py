"""
IELTS Listening API Router.

Endpoints:
- GET  /listening                 → generate a full listening test (Gemini + audio blocks + TTS)
- GET  /listening/generated       → list previously generated tests
- GET  /listening/generated/{fn}  → retrieve a specific test by filename
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse

from services.listening_service import ListeningTestService, get_listening_service
from core.exceptions import (
    GeminiAPIError,
    JSONParseError,
    SchemaValidationError,
    IELTSAPIException,
)

# ── Logger ────────────────────────────────────────────────────────────
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

router = APIRouter()

# ── Paths ─────────────────────────────────────────────────────────────
GENERATED_LISTENING_DIR = Path(__file__).parent.parent / "data" / "generated" / "listening"


# ── Helpers ───────────────────────────────────────────────────────────
def _save_generated_test(test_data: Dict[str, Any]) -> str:
    """Persist the generated test JSON with a timestamped filename."""
    save_dir = GENERATED_LISTENING_DIR
    save_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"listening_{timestamp}.json"
    filepath = save_dir / filename

    with open(filepath, "w", encoding="utf-8") as fh:
        json.dump(test_data, fh, indent=2, ensure_ascii=False)

    logger.info(f"Saved listening test to {filepath}")
    return str(filepath)


# =====================================================================
# Generate
# =====================================================================
@router.get(
    "/listening",
    summary="Generate IELTS Listening Test",
    description="""
    Generate a complete IELTS Listening test:
    - 4 sections, 40 questions (via Gemini AI)
    - 8 audio blocks with transcript chunks
    - MP3 audio rendered per block / accent via edge-tts

    Returns the full test JSON including audio_blocks, answer_key, etc.
    """,
    response_description="Complete IELTS Listening test JSON",
    responses={
        200: {
            "description": "Successfully generated IELTS Listening test",
            "content": {
                "application/json": {
                    "example": {
                        "test_id": "a1b2c3d4",
                        "test_type": "IELTS Academic Listening",
                        "total_questions": 40,
                        "audio_duration_minutes": 30,
                        "audio_blocks": ["… 8 blocks …"],
                        "answer_key": {"1": "example", "": ""},
                    }
                }
            },
        },
        400: {"description": "Invalid request parameters"},
        500: {"description": "Internal server error or schema validation failed"},
        502: {"description": "Gemini API error"},
    },
)
async def generate_listening_test(
    difficulty: str = Query(
        default="7.0",
        description="Target IELTS band difficulty (5.0-9.0)",
        regex=r"^(5\.0|5\.5|6\.0|6\.5|7\.0|7\.5|8\.0|8\.5|9\.0)$",
    ),
    listening_service: ListeningTestService = Depends(get_listening_service),
) -> Dict[str, Any]:
    """Generate a complete IELTS Listening test with 8 audio blocks."""
    logger.info(f"=== Listening Test Generation Request === difficulty={difficulty}")

    try:
        output_dir = str(GENERATED_LISTENING_DIR)

        test_data = await listening_service.generate_test(
            difficulty=difficulty,
            output_dir=output_dir,
        )
        logger.info("Listening test generation completed")

        # Persist
        saved = _save_generated_test(test_data)
        logger.info(f"Test saved to {saved}")

        # Summary log
        blocks = test_data.get("audio_blocks", [])
        ok = sum(
            1
            for b in blocks
            for a in b.get("audio_assets", {}).values()
            if isinstance(a, dict) and a.get("status") == "generated"
        )
        fail = sum(
            1
            for b in blocks
            for a in b.get("audio_assets", {}).values()
            if isinstance(a, dict) and a.get("status", "").startswith("failed")
        )
        logger.info(f"Audio: {ok} generated, {fail} failed")

        return test_data

    except SchemaValidationError as exc:
        logger.error(f"Schema validation error: {exc.message}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Schema Validation Error",
                "message": exc.message,
                "details": exc.details,
            },
        )
    except JSONParseError as exc:
        logger.error(f"JSON parse error: {exc.message}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "JSON Parse Error",
                "message": exc.message,
                "details": exc.details,
            },
        )
    except GeminiAPIError as exc:
        logger.error(f"Gemini API error: {exc.message}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Gemini API Error",
                "message": exc.message,
                "details": exc.details,
            },
        )
    except IELTSAPIException as exc:
        logger.error(f"IELTS API error: {exc.message}", exc_info=True)
        raise HTTPException(
            status_code=exc.status_code,
            detail={
                "error": "IELTS API Error",
                "message": exc.message,
                "details": exc.details,
            },
        )
    except Exception as exc:
        logger.error(f"Unexpected error: {exc}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={"error": "Internal Server Error", "message": str(exc)},
        )


# =====================================================================
# List generated tests
# =====================================================================
@router.get(
    "/listening/generated",
    summary="List Generated Listening Tests",
    description="List all previously generated listening tests with timestamps.",
)
async def list_generated_listening_tests() -> Dict[str, Any]:
    if not GENERATED_LISTENING_DIR.exists():
        return {"tests": [], "total_count": 0}

    tests = []
    for fp in sorted(GENERATED_LISTENING_DIR.glob("listening_*.json"), reverse=True):
        parts = fp.stem.split("_")
        if len(parts) >= 3:
            d, t = parts[1], parts[2]
            ts = f"{d[:4]}-{d[4:6]}-{d[6:8]} {t[:2]}:{t[2:4]}:{t[4:6]}"
        else:
            ts = "Unknown"
        tests.append({
            "filename": fp.name,
            "timestamp": ts,
            "size_kb": round(fp.stat().st_size / 1024, 2),
        })

    return {"tests": tests, "total_count": len(tests)}


# =====================================================================
# Get a specific generated test
# =====================================================================
@router.get(
    "/listening/generated/{filename}",
    summary="Get Generated Listening Test",
    description="Retrieve a previously generated listening test by filename.",
)
async def get_generated_listening_test(filename: str) -> Dict[str, Any]:
    filepath = GENERATED_LISTENING_DIR / filename

    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Test file not found: {filename}")
    if not filepath.resolve().is_relative_to(GENERATED_LISTENING_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")

    with open(filepath, "r", encoding="utf-8") as fh:
        return json.load(fh)


# =====================================================================
# Serve audio file
# =====================================================================
@router.get(
    "/listening/audio/{test_id}/{block_dir}/{accent_file}",
    summary="Stream Listening Audio",
    description="Serve an MP3 audio file for a specific block and accent.",
)
async def get_listening_audio(
    test_id: str,
    block_dir: str,
    accent_file: str,
) -> FileResponse:
    """Return the MP3 file for a given test / block / accent."""
    audio_path = (
        GENERATED_LISTENING_DIR
        / "audio"
        / "listening"
        / test_id
        / block_dir
        / accent_file
    )

    if not audio_path.exists():
        raise HTTPException(status_code=404, detail="Audio file not found")
    if not audio_path.resolve().is_relative_to(GENERATED_LISTENING_DIR.resolve()):
        raise HTTPException(status_code=400, detail="Invalid path")

    return FileResponse(
        path=str(audio_path),
        media_type="audio/mpeg",
        filename=accent_file,
    )
