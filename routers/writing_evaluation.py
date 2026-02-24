"""
IELTS Writing Evaluation API Router.
Provides endpoints for evaluating user-submitted IELTS Writing responses.
"""

import logging
from typing import Any, Dict

from fastapi import APIRouter, Depends, HTTPException

from services.writing_evaluation_service import (
    WritingEvaluationService,
    get_writing_evaluation_service
)
from schemas.writing_evaluation import (
    WritingEvaluationRequest,
    WritingEvaluationResponse
)
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


@router.post(
    "/writing/evaluate",
    summary="Evaluate IELTS Writing Response",
    description="""
    Evaluate a user's IELTS Writing response using AI-powered IELTS examiner assessment.
    
    The evaluation follows official IELTS assessment criteria:
    - Task Achievement (Task 1) / Task Response (Task 2)
    - Coherence and Cohesion
    - Lexical Resource
    - Grammatical Range and Accuracy
    
    Each criterion is scored independently on a 0-9 band scale, and the overall band
    is calculated as the average rounded to the nearest 0.5.
    
    Requirements:
    - Response must be at least 50 words
    - Task number must be 1 or 2
    - Module must be "Academic" or "General Training"
    
    The evaluation provides:
    - Band scores for each criterion with specific feedback
    - Overall band score
    - Summary of strengths and weaknesses
    - Actionable improvement suggestions
    """,
    response_model=WritingEvaluationResponse,
    response_description="Evaluation results with band scores and feedback",
    responses={
        200: {
            "description": "Successfully evaluated the writing response",
            "content": {
                "application/json": {
                    "example": {
                        "success": True,
                        "evaluation": {
                            "task_number": 2,
                            "overall_band": 7.0,
                            "task_achievement_or_response": {
                                "band": 7,
                                "feedback": "The response addresses all parts of the prompt..."
                            },
                            "coherence_and_cohesion": {
                                "band": 7,
                                "feedback": "Ideas are logically organized..."
                            },
                            "lexical_resource": {
                                "band": 7,
                                "feedback": "A sufficient range of vocabulary..."
                            },
                            "grammatical_range_and_accuracy": {
                                "band": 6,
                                "feedback": "A mix of simple and complex sentences..."
                            },
                            "strengths": "Clear thesis, good examples...",
                            "weaknesses": "Some grammatical errors...",
                            "improvement_suggestions": "Focus on proofreading..."
                        },
                        "word_count": 287,
                        "task_number": 2,
                        "module": "Academic"
                    }
                }
            }
        },
        400: {
            "description": "Invalid request - response too short, invalid task number, or invalid module",
            "content": {
                "application/json": {
                    "example": {
                        "error": "Schema Validation Error",
                        "message": "Input validation failed",
                        "details": {
                            "errors": ["Response too short: 45 words. Minimum required: 50 words."]
                        }
                    }
                }
            }
        },
        500: {"description": "Internal server error or evaluation processing failed"},
        502: {"description": "Gemini API error"}
    }
)
async def evaluate_writing_response(
    request: WritingEvaluationRequest,
    evaluation_service: WritingEvaluationService = Depends(get_writing_evaluation_service)
) -> WritingEvaluationResponse:
    """
    Evaluate a user's IELTS Writing response.
    
    Accepts the user's response and task details, returns a comprehensive
    evaluation with band scores and feedback for each criterion.
    """
    logger.info(f"=== Writing Evaluation Request ===")
    logger.info(f"Task: {request.task_number}, Module: {request.module}, Difficulty: {request.difficulty}")
    logger.info(f"Response length: {len(request.user_response)} characters")
    
    try:
        # Perform evaluation
        evaluation_result = await evaluation_service.evaluate_response(
            user_response=request.user_response,
            task_number=request.task_number,
            module=request.module,
            difficulty=request.difficulty,
            task_prompt=request.task_prompt
        )
        
        # Calculate word count
        word_count = len(request.user_response.strip().split())
        
        # Build response
        response = WritingEvaluationResponse(
            success=True,
            evaluation=evaluation_result,
            word_count=word_count,
            task_number=request.task_number,
            module=request.module
        )
        
        logger.info(f"=== Evaluation Response Summary ===")
        logger.info(f"Overall Band: {evaluation_result['overall_band']}")
        logger.info(f"Word Count: {word_count}")
        
        return response
    
    except SchemaValidationError as e:
        logger.error(f"Schema validation error: {e.message}", exc_info=True)
        raise HTTPException(
            status_code=400,
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
        logger.error(f"Unexpected error during evaluation: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail={
                "error": "Internal Server Error",
                "message": f"Failed to evaluate response: {str(e)}"
            }
        )
