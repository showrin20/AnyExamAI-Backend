"""
IELTS Reading API Router.
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, Query

from services.reading_service import ReadingTestService, get_reading_service
from core.exceptions import (
    GeminiAPIError,
    JSONParseError,
    SchemaValidationError,
    IELTSAPIException
)

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

router = APIRouter()


USED_TOPICS_FILE = Path(__file__).parent.parent / "data" / "used_topics.json"
GENERATED_READING_DIR = Path(__file__).parent.parent / "data" / "generated" / "reading"


def save_generated_test(test_data: Dict[str, Any], test_type: str = "reading") -> str:
    """
    Save generated test data to a JSON file with timestamp.
    
    Args:
        test_data: The generated test data to save
        test_type: Type of test (reading/writing)
        
    Returns:
        The filepath where the test was saved
    """
    # Create directory if it doesn't exist
    save_dir = Path(__file__).parent.parent / "data" / "generated" / test_type
    save_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate filename with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"{test_type}_{timestamp}.json"
    filepath = save_dir / filename
    
    # Save the test data
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(test_data, f, indent=2, ensure_ascii=False)
    
    logger.info(f"Saved generated {test_type} test to: {filepath}")
    return str(filepath)


def load_used_topics() -> List[str]:
    """Load previously used topics from a JSON file."""
    logger.debug(f"Loading used topics from {USED_TOPICS_FILE}")
    if USED_TOPICS_FILE.exists():
        try:
            with open(USED_TOPICS_FILE, "r") as f:
                topics = json.load(f)
                logger.info(f"Loaded {len(topics)} used topics")
                return topics
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error loading used topics: {e}")
            return []
    logger.info("No used topics file found, starting fresh")
    return []


def save_used_topics(topics: List[str]) -> None:
    """Save previously used topics to a JSON file."""
    logger.debug(f"Saving {len(topics)} used topics to {USED_TOPICS_FILE}")
    USED_TOPICS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(USED_TOPICS_FILE, "w") as f:  # Fixed: "w" not "W"
        json.dump(topics, f, indent=2)
    logger.info(f"Saved {len(topics)} used topics")


def add_topics_to_history(new_topics: List[str], max_history: int = 1000) -> None:
    """Add new topics to the history of used topics, ensuring no duplicates and keeping only the last max_history."""
    logger.info(f"Adding {len(new_topics)} new topics to history: {new_topics}")
    used_topics = load_used_topics()
    used_topics.extend(new_topics)
    if len(used_topics) > max_history:
        used_topics = used_topics[-max_history:]
        logger.info(f"Trimmed topics history to {max_history} entries")
    save_used_topics(used_topics)


@router.get(
    "/reading",
    summary="Generate IELTS Reading Test",
    description="""
    Generate a complete IELTS Academic Reading test using Gemini AI.
    Topics are automatically selected by Gemini AI, ensuring no repetition
    of previously used topics.

    The test follows the official IELTS schema v2.0 specification:
    - 3 passages with progressive difficulty
    - 40 questions total (approximately 13-14 per passage)
    - 60 minutes duration
    - Various question types (multiple choice, T/F/NG, matching, completion, etc.)
    
    Returns the raw test JSON that can be directly used by the frontend.
    """,
    response_description="Complete IELTS Reading test JSON",
    responses={
        200: {
            "description": "Successfully generated IELTS Reading test",
            "content": {
                "application/json": {
                    "example": {
                        "test_type": "IELTS Academic",
                        "total_questions": 40,
                        "total_duration_minutes": 60,
                        "test_metadata": {
                            "schema_version": "2.0",
                            "generated_at": "2026-02-24T10:00:00",
                            "difficulty_band": "7.0",
                            "topics": ["Marine Biology", "Artificial Intelligence", "Climate Change"]
                        },
                        "passages": ["..."],
                        "answer_key": {"1": "A", "2": "True", "...": "..."}
                    }
                }
            }
        },
        400: {"description": "Invalid request parameters"},
        500: {"description": "Internal server error or schema validation failed"},
        502: {"description": "Gemini API error"}
    }
)
async def generate_reading_test(
    difficulty: str = Query(
        default="7.0",
        description="Target IELTS band difficulty (5.0-9.0)",
        regex=r"^(5\.0|5\.5|6\.0|6\.5|7\.0|7\.5|8\.0|8\.5|9\.0)$"
    ),
    reading_service: ReadingTestService = Depends(get_reading_service)
) -> Dict[str, Any]:
    """
    Generate a complete IELTS Academic Reading test.
    
    Topics are automatically selected by Gemini AI, avoiding previously used topics.
    Returns the raw structured IELTS test JSON expected by the frontend.
    """
    logger.info(f"=== Reading Test Generation Request ===")
    logger.info(f"Difficulty: {difficulty}")
    
    try:
        # Load previously used topics to avoid repetition
        used_topics = load_used_topics()
        logger.info(f"Loaded {len(used_topics)} previously used topics")
        
        # Generate the test with exclude_topics
        logger.info("Starting test generation...")
        test_data = await reading_service.generate_test(
            difficulty=difficulty,
            exclude_topics=used_topics
        )
        logger.info("Test generation completed successfully")

        # Extract topics from generated test and add to history
        if "test_metadata" in test_data and "topics" in test_data["test_metadata"]:
            new_topics = test_data["test_metadata"]["topics"]
            logger.info(f"New topics generated: {new_topics}")
            add_topics_to_history(new_topics)

        # Save the generated test to file
        saved_filepath = save_generated_test(test_data, "reading")
        logger.info(f"Test saved to: {saved_filepath}")

        # Log response summary
        logger.info(f"=== Response Summary ===")
        logger.info(f"Test type: {test_data.get('test_type')}")
        logger.info(f"Total questions: {test_data.get('total_questions')}")
        logger.info(f"Passages: {len(test_data.get('passages', []))}")
        for i, passage in enumerate(test_data.get('passages', []), 1):
            logger.info(f"  Passage {i}: '{passage.get('heading', 'No title')}' - {len(passage.get('questions', []))} questions")
        
        # Return raw test JSON (no wrapper)
        return test_data
    
    except SchemaValidationError as e:
        logger.error(f"Schema validation error: {e.message}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Schema Validation Error",
                "message": e.message,
                "details": e.details
            }
        )
    
    except JSONParseError as e:
        logger.error(f"JSON parse error: {e.message}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "JSON Parse Error",
                "message": e.message,
                "details": e.details
            }
        )
    
    except GeminiAPIError as e:
        logger.error(f"Gemini API error: {e.message}", exc_info=True)
        raise HTTPException(
            status_code=502,
            detail={
                "error": "Gemini API Error",
                "message": e.message,
                "details": e.details
            }
        )
    
    except IELTSAPIException as e:
        logger.error(f"IELTS API error: {e.message}", exc_info=True)
        raise HTTPException(
            status_code=e.status_code,
            detail={
                "error": "IELTS API Error",
                "message": e.message,
                "details": e.details
            }
        )
    
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal Server Error",
                "message": str(e)
            }
        )


@router.delete(
    "/reading/topics/history",  # Fixed typo: "hustory" -> "history"
    summary="Clear Topic History",
    description="Clear the history of used topics for IELTS Reading test generation.",
)
async def clear_topic_history() -> Dict[str, str]:
    """Clear the used topic history."""
    save_used_topics([])
    return {"message": "Topic history cleared successfully."}


@router.get(
    "/reading/topics/history",
    summary="Get Topic History",
    description="Get the history of used topics for IELTS Reading test generation.",
)
async def get_topic_history() -> Dict[str, Any]:
    """Get the used topic history."""
    used_topics = load_used_topics()
    return {
        "total_count": len(used_topics),
        "topics": used_topics
    }


@router.get(
    "/reading/generated",
    summary="List Generated Reading Tests",
    description="List all previously generated reading tests with their timestamps.",
)
async def list_generated_reading_tests() -> Dict[str, Any]:
    """List all generated reading tests."""
    save_dir = Path(__file__).parent.parent / "data" / "generated" / "reading"
    
    if not save_dir.exists():
        return {"tests": [], "total_count": 0}
    
    tests = []
    for filepath in sorted(save_dir.glob("*.json"), reverse=True):
        # Extract timestamp from filename (reading_20260224_153045.json)
        filename = filepath.stem
        parts = filename.split("_")
        if len(parts) >= 3:
            date_str = parts[1]
            time_str = parts[2]
            timestamp = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]} {time_str[:2]}:{time_str[2:4]}:{time_str[4:6]}"
        else:
            timestamp = "Unknown"
        
        tests.append({
            "filename": filepath.name,
            "timestamp": timestamp,
            "size_kb": round(filepath.stat().st_size / 1024, 2)
        })
    
    return {
        "tests": tests,
        "total_count": len(tests)
    }


@router.get(
    "/reading/generated/{filename}",
    summary="Get Generated Reading Test",
    description="Retrieve a previously generated reading test by filename.",
)
async def get_generated_reading_test(filename: str) -> Dict[str, Any]:
    """Get a specific generated reading test."""
    save_dir = Path(__file__).parent.parent / "data" / "generated" / "reading"
    filepath = save_dir / filename
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Test file not found: {filename}")
    
    # Security check - ensure the file is within the expected directory
    if not filepath.resolve().is_relative_to(save_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    with open(filepath, "r", encoding="utf-8") as f:
        test_data = json.load(f)
    
    return test_data