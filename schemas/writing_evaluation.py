"""
Pydantic schemas for IELTS Writing Evaluation.
These schemas define the structure for evaluating user-submitted writing responses.
"""

from typing import Literal, Optional
from pydantic import BaseModel, Field, field_validator


class CriterionScore(BaseModel):
    """Score and feedback for a single assessment criterion."""
    band: int = Field(..., ge=0, le=9, description="Band score from 0 to 9")
    feedback: str = Field(
        ..., 
        min_length=20, 
        description="Detailed feedback referencing the response"
    )


class WritingEvaluation(BaseModel):
    """
    Complete evaluation result for an IELTS Writing task.
    
    This schema validates the evaluation output from the Gemini API,
    ensuring all criteria are scored and proper feedback is provided.
    """
    task_number: Literal[1, 2] = Field(
        ..., 
        description="Task number being evaluated (1 or 2)"
    )
    overall_band: float = Field(
        ..., 
        ge=0.0, 
        le=9.0, 
        description="Overall band score (0-9, rounded to nearest 0.5)"
    )
    task_achievement_or_response: CriterionScore = Field(
        ..., 
        description="Task Achievement (Task 1) or Task Response (Task 2)"
    )
    coherence_and_cohesion: CriterionScore = Field(
        ..., 
        description="Coherence and Cohesion assessment"
    )
    lexical_resource: CriterionScore = Field(
        ..., 
        description="Lexical Resource assessment"
    )
    grammatical_range_and_accuracy: CriterionScore = Field(
        ..., 
        description="Grammatical Range and Accuracy assessment"
    )
    strengths: str = Field(
        ..., 
        min_length=10, 
        description="Summary of the response's strengths"
    )
    weaknesses: str = Field(
        ..., 
        min_length=10, 
        description="Summary of the response's weaknesses"
    )
    improvement_suggestions: str = Field(
        ..., 
        min_length=10, 
        description="Specific suggestions for improvement"
    )

    @field_validator('overall_band')
    @classmethod
    def validate_band_increment(cls, v: float) -> float:
        """Ensure overall band is rounded to nearest 0.5."""
        rounded = round(v * 2) / 2
        if rounded != v:
            # Auto-correct to nearest 0.5
            return rounded
        return v

    class Config:
        json_schema_extra = {
            "example": {
                "task_number": 2,
                "overall_band": 7.0,
                "task_achievement_or_response": {
                    "band": 7,
                    "feedback": "The response addresses all parts of the prompt with a clear position throughout. Ideas are relevant and well-developed with appropriate examples."
                },
                "coherence_and_cohesion": {
                    "band": 7,
                    "feedback": "Ideas are logically organized with clear progression. Paragraphing is appropriate and cohesive devices are used effectively."
                },
                "lexical_resource": {
                    "band": 7,
                    "feedback": "A sufficient range of vocabulary is used with some awareness of style and collocation. Occasional errors in word choice do not impede communication."
                },
                "grammatical_range_and_accuracy": {
                    "band": 6,
                    "feedback": "A mix of simple and complex sentence forms is used. Some grammatical errors occur but they rarely reduce communication."
                },
                "strengths": "Clear thesis statement, good use of examples, logical paragraph structure, and varied vocabulary.",
                "weaknesses": "Some grammatical errors with complex structures, occasional word choice issues, and conclusion could be more developed.",
                "improvement_suggestions": "Focus on proofreading for grammatical accuracy, especially with complex sentences. Develop the conclusion to provide a stronger summary of the main points."
            }
        }


class WritingEvaluationRequest(BaseModel):
    """
    Request schema for submitting a writing response for evaluation.
    """
    user_response: str = Field(
        ..., 
        min_length=1, 
        description="The user's written response to evaluate"
    )
    task_number: Literal[1, 2] = Field(
        ..., 
        description="Task number (1 or 2)"
    )
    module: Literal["Academic", "General Training"] = Field(
        default="Academic", 
        description="IELTS module type"
    )
    difficulty: str = Field(
        default="7.0",
        pattern=r"^(5\.0|5\.5|6\.0|6\.5|7\.0|7\.5|8\.0|8\.5|9\.0)$",
        description="Target difficulty band for context"
    )
    task_prompt: Optional[str] = Field(
        default=None,
        description="Optional: The original task prompt for more accurate evaluation"
    )

    @field_validator('user_response')
    @classmethod
    def validate_response_not_empty(cls, v: str) -> str:
        """Ensure response is not just whitespace."""
        stripped = v.strip()
        if not stripped:
            raise ValueError("Response cannot be empty or contain only whitespace")
        return stripped

    class Config:
        json_schema_extra = {
            "example": {
                "user_response": "In today's rapidly evolving world, the debate over whether governments should prioritize economic growth or environmental protection has become increasingly pertinent...",
                "task_number": 2,
                "module": "Academic",
                "difficulty": "7.0",
                "task_prompt": "Some people believe that economic growth is the only way to end hunger and poverty, while others say that economic growth damages the environment so much that it must be stopped. Discuss both views and give your own opinion."
            }
        }


class WritingEvaluationResponse(BaseModel):
    """
    Response wrapper for writing evaluation results.
    """
    success: bool = Field(default=True, description="Whether evaluation was successful")
    evaluation: WritingEvaluation = Field(..., description="The evaluation results")
    word_count: int = Field(..., ge=0, description="Word count of the submitted response")
    task_number: Literal[1, 2] = Field(..., description="Task number evaluated")
    module: str = Field(..., description="Module type used for evaluation")

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "evaluation": {
                    "task_number": 2,
                    "overall_band": 7.0,
                    "task_achievement_or_response": {"band": 7, "feedback": "..."},
                    "coherence_and_cohesion": {"band": 7, "feedback": "..."},
                    "lexical_resource": {"band": 7, "feedback": "..."},
                    "grammatical_range_and_accuracy": {"band": 6, "feedback": "..."},
                    "strengths": "...",
                    "weaknesses": "...",
                    "improvement_suggestions": "..."
                },
                "word_count": 287,
                "task_number": 2,
                "module": "Academic"
            }
        }
