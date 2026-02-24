"""
Pydantic schemas for IELTS Writing test.
These schemas match the existing JSON structure used by the frontend (schema v3.0).
"""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


# === Visual Data for Academic Task 1 ===

class VisualData(BaseModel):
    """Visual data for Academic Task 1 (charts, diagrams, etc.)."""
    chart_type: Literal[
        "Line Graph", "Bar Chart", "Pie Chart", "Table",
        "Process Diagram", "Map", "Mixed Chart", "Flow Chart"
    ]
    title: str
    description_text: str
    data_points: Optional[List[Dict[str, Any]]] = None
    time_period: Optional[str] = None
    units: Optional[str] = None


# === Letter Context for General Training Task 1 ===

class LetterContext(BaseModel):
    """Letter context for General Training Task 1."""
    situation: str
    purpose: Literal[
        "Request", "Complaint", "Apology", "Recommendation",
        "Enquiry", "Application", "Invitation", "Persuasion"
    ]
    recipient_type: Literal["Friend", "Family Member", "Organization", "Manager", "Authority"]
    formality_level: Literal["Formal", "Semi-Formal", "Informal"]
    bullet_points: Optional[List[str]] = None


# === Essay Context for Task 2 ===

class EssayContext(BaseModel):
    """Essay context for Task 2."""
    topic: str
    essay_type: Literal["Opinion", "Discussion", "Problem_Solution", "Advantages_Disadvantages"]
    question_prompt: str
    key_topics: Optional[List[str]] = None


# === Task Prompt ===

class TaskPrompt(BaseModel):
    """Prompt details for a writing task."""
    task_instruction: str
    context_information: Optional[str] = None
    visual_data: Optional[VisualData] = None
    letter_context: Optional[LetterContext] = None
    essay_context: Optional[EssayContext] = None


# === Assessment Breakdown ===

class AssessmentBreakdown(BaseModel):
    """Assessment breakdown for sample responses."""
    task_achievement_or_response: str
    coherence_and_cohesion: str
    lexical_resource: str
    grammatical_range_and_accuracy: str


# === Sample Response ===

class SampleResponse(BaseModel):
    """Sample response with examiner commentary."""
    band_score: int = Field(..., ge=1, le=9)
    word_count: int = Field(..., ge=50)
    response_text: str = Field(..., min_length=100)
    examiner_commentary: str
    assessment_breakdown: AssessmentBreakdown


# === Writing Task ===

class WritingTask(BaseModel):
    """Schema for a single writing task."""
    task_number: Literal[1, 2]
    task_type: Literal[
        "Report_Chart", "Report_Process", "Report_Map",
        "Letter_Informal", "Letter_Formal", "Letter_SemiFormal",
        "Essay_Opinion", "Essay_Discussion", 
        "Essay_Problem_Solution", "Essay_Advantages_Disadvantages"
    ]
    module_specific: Literal["Academic", "General Training"]
    minimum_word_count: Literal[150, 250]
    recommended_word_count: Optional[int] = None
    assessment_weight: Literal["33%", "67%"]
    instructions: str
    task_context: Optional[str] = None
    prompt: TaskPrompt
    sample_responses: List[SampleResponse] = Field(..., min_length=1)


# === Time Split ===

class RecommendedTimeSplit(BaseModel):
    """Recommended time allocation."""
    task_1_minutes: int = 20
    task_2_minutes: int = 40


# === Test Metadata ===

class WritingTestMetadata(BaseModel):
    """Metadata for the writing test."""
    schema_version: str = "3.0"
    generated_at: str
    difficulty_band: str = Field(
        ...,
        pattern=r"^(5\.0|5\.5|6\.0|6\.5|7\.0|7\.5|8\.0|8\.5|9\.0)$"
    )
    test_source: str


# === Scoring Methodology ===

class TaskWeighting(BaseModel):
    """Task weighting information."""
    task_1_weight: str = "33%"
    task_2_weight: str = "67%"


class ScoringMethodology(BaseModel):
    """Scoring methodology details."""
    description: str
    task_weighting: TaskWeighting
    criterion_weighting: Optional[str] = None


# === Band Scale ===

class BandDescriptor(BaseModel):
    """Band scale descriptor."""
    band: int = Field(..., ge=0, le=9)
    skill_level: str
    descriptor: str


# === Detailed Rubrics ===

class CriterionRubric(BaseModel):
    """Rubric for a single criterion."""
    band_9: Optional[str] = None
    band_8: Optional[str] = None
    band_7: Optional[str] = None
    band_6: Optional[str] = None
    band_5: Optional[str] = None
    band_4: Optional[str] = None
    band_3: Optional[str] = None


class DetailedRubrics(BaseModel):
    """Detailed rubrics for all criteria."""
    task_achievement_task_1: Optional[CriterionRubric] = Field(None, alias="Task Achievement (Task 1)")
    task_response_task_2: Optional[CriterionRubric] = Field(None, alias="Task Response (Task 2)")
    coherence_and_cohesion: Optional[CriterionRubric] = Field(None, alias="Coherence and Cohesion")
    lexical_resource: Optional[CriterionRubric] = Field(None, alias="Lexical Resource")
    grammatical_range_and_accuracy: Optional[CriterionRubric] = Field(None, alias="Grammatical Range and Accuracy")

    class Config:
        populate_by_name = True


# === Assessment ===

class Assessment(BaseModel):
    """Assessment criteria and scoring information."""
    criteria: List[str]
    scoring_methodology: ScoringMethodology
    band_scale: List[BandDescriptor]
    detailed_rubrics: Optional[Dict[str, Any]] = None


# === Complete Writing Test Schema ===

class IELTSWritingTest(BaseModel):
    """Complete IELTS Writing Test schema matching frontend expectations (v3.0)."""
    test_name: Literal["IELTS Writing"] = "IELTS Writing"
    module: Literal["Academic", "General Training"]
    total_time_minutes: Literal[60] = 60
    recommended_time_split: Optional[RecommendedTimeSplit] = None
    test_metadata: WritingTestMetadata
    tasks: List[WritingTask] = Field(..., min_length=2, max_length=2)
    assessment: Assessment

    class Config:
        json_schema_extra = {
            "example": {
                "test_name": "IELTS Writing",
                "module": "Academic",
                "total_time_minutes": 60,
                "recommended_time_split": {
                    "task_1_minutes": 20,
                    "task_2_minutes": 40
                },
                "test_metadata": {
                    "schema_version": "3.0",
                    "generated_at": "2026-02-24T10:00:00",
                    "difficulty_band": "7.0",
                    "test_source": "AI Generated Practice Test"
                },
                "tasks": [],
                "assessment": {}
            }
        }
