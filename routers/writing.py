"""
IELTS Writing API Router.
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Literal

from fastapi import APIRouter, Depends, HTTPException, Query

from services.writing_service import WritingTestService, get_writing_service
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


def save_generated_test(test_data: Dict[str, Any], test_type: str = "writing") -> str:
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


@router.get(
    "/writing",
    summary="Generate IELTS Writing Test",
    description="""
    Generate a complete IELTS Writing test using Gemini AI.
    
    The test follows the official IELTS schema v3.0 specification:
    - 2 tasks (Task 1: Report/Letter, Task 2: Essay)
    - 60 minutes total duration
    - Task 1: 150 words minimum (20 minutes recommended)
    - Task 2: 250 words minimum (40 minutes recommended)
    - Sample responses at bands 8, 6, and 4 with examiner commentary
    - Full assessment criteria and rubrics
    
    Returns the raw test JSON that can be directly used by the frontend.
    """,
    response_description="Complete IELTS Writing test JSON",
    responses={
        200: {
            "description": "Successfully generated IELTS Writing test",
            "content": {
                "application/json": {
                    "example": {
                        "test_name": "IELTS Writing",
                        "module": "Academic",
                        "total_time_minutes": 60,
                        "test_metadata": {
                            "schema_version": "3.0",
                            "generated_at": "2026-02-24T10:00:00",
                            "difficulty_band": "7.0"
                        },
                        "tasks": ["..."],
                        "assessment": {"...": "..."}
                    }
                }
            }
        },
        400: {"description": "Invalid request parameters"},
        500: {"description": "Internal server error or schema validation failed"},
        502: {"description": "Gemini API error"}
    }
)
async def generate_writing_test(
    module: Literal["Academic", "General Training"] = Query(
        default="Academic",
        description="IELTS module type. Academic or General Training.",
        example="Academic"
    ),
    difficulty: str = Query(
        default="7.0",
        description="Target IELTS band difficulty (5.0-9.0 with 0.5 increments)",
        regex=r"^(5\.0|5\.5|6\.0|6\.5|7\.0|7\.5|8\.0|8\.5|9\.0)$"
    ),
    writing_service: WritingTestService = Depends(get_writing_service)
) -> Dict[str, Any]:
    """
    Generate a complete IELTS Writing test.
    
    Returns the raw structured IELTS test JSON expected by the frontend.
    No wrapper object - returns the exam JSON directly.
    """
    logger.info(f"=== Writing Test Generation Request ===")
    logger.info(f"Module: {module}, Difficulty: {difficulty}")
    
    try:
        # Generate the test
        logger.info("Starting test generation...")
        test_data = await writing_service.generate_test(
            module=module,
            difficulty=difficulty
        )
        logger.info("Test generation completed successfully")
        
        # Save the generated test to file
        saved_filepath = save_generated_test(test_data, "writing")
        logger.info(f"Test saved to: {saved_filepath}")
        
        # Log response summary
        logger.info(f"=== Response Summary ===")
        logger.info(f"Test name: {test_data.get('test_name')}")
        logger.info(f"Module: {test_data.get('module')}")
        logger.info(f"Total time: {test_data.get('total_time_minutes')} minutes")
        logger.info(f"Tasks: {len(test_data.get('tasks', []))}")
        for i, task in enumerate(test_data.get('tasks', []), 1):
            logger.info(f"  Task {i}: type={task.get('task_type')}, samples={len(task.get('sample_responses', []))}")
        
        # Return raw test JSON (no wrapper)
        return test_data
    
    except SchemaValidationError as e:
        logger.error(f"Schema validation error: {e.message}")
        logger.error(f"Schema validation details: {e.details}")
        raise HTTPException(
            status_code=400 if "module" in str(e.message).lower() else 500,
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


@router.get(
    "/writing/generated",
    summary="List Generated Writing Tests",
    description="List all previously generated writing tests with their timestamps.",
)
async def list_generated_writing_tests() -> Dict[str, Any]:
    """List all generated writing tests."""
    save_dir = Path(__file__).parent.parent / "data" / "generated" / "writing"
    
    if not save_dir.exists():
        return {"tests": [], "total_count": 0}
    
    tests = []
    for filepath in sorted(save_dir.glob("*.json"), reverse=True):
        # Extract timestamp from filename (writing_20260224_153045.json)
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
    "/writing/generated/{filename}",
    summary="Get Generated Writing Test",
    description="Retrieve a previously generated writing test by filename.",
)
async def get_generated_writing_test(filename: str) -> Dict[str, Any]:
    """Get a specific generated writing test."""
    save_dir = Path(__file__).parent.parent / "data" / "generated" / "writing"
    filepath = save_dir / filename
    
    if not filepath.exists():
        raise HTTPException(status_code=404, detail=f"Test file not found: {filename}")
    
    # Security check - ensure the file is within the expected directory
    if not filepath.resolve().is_relative_to(save_dir.resolve()):
        raise HTTPException(status_code=400, detail="Invalid filename")
    
    with open(filepath, "r", encoding="utf-8") as f:
        test_data = json.load(f)
    
    return test_data
