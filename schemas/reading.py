"""
Pydantic schemas for IELTS Reading test.
These schemas match the existing JSON structure used by the frontend.
"""

from typing import Any, Dict, List, Literal, Optional, Union
from pydantic import BaseModel, Field


# === Question Types ===

class BaseQuestion(BaseModel):
    """Base question model with common fields."""
    question_number: int = Field(..., ge=1, le=40)
    type: str
    answer: Union[str, int, List[str]]
    difficulty_band: Optional[str] = None
    explanation: Optional[str] = None


class MultipleChoiceQuestion(BaseQuestion):
    """Multiple choice question type."""
    type: Literal["multiple_choice"] = "multiple_choice"
    question_text: str
    options: List[str] = Field(..., min_length=4, max_length=4)
    answer: str


class IdentifyingInformationQuestion(BaseQuestion):
    """True/False/Not Given question type."""
    type: Literal["identifying_information"] = "identifying_information"
    statement: str
    answer: Literal["True", "False", "Not Given"]


class IdentifyingWriterViewQuestion(BaseQuestion):
    """Yes/No/Not Given question type."""
    type: Literal["identifying_writer_view"] = "identifying_writer_view"
    statement: str
    answer: Literal["Yes", "No", "Not Given"]


class ShortAnswerQuestion(BaseQuestion):
    """Short answer question type."""
    type: Literal["short_answer"] = "short_answer"
    question_text: str
    max_word_count: int = Field(default=3, ge=1, le=5)
    answer: str


class SentenceCompletionQuestion(BaseQuestion):
    """Sentence completion question type."""
    type: Literal["sentence_completion"] = "sentence_completion"
    incomplete_sentence: str
    options: Optional[List[str]] = None
    answer: str


class SummaryCompletionQuestion(BaseQuestion):
    """Summary completion question type."""
    type: Literal["summary_completion"] = "summary_completion"
    summary_text: str
    max_word_count: Optional[int] = Field(default=2, ge=1, le=3)
    answer: str


class MatchingHeadingsQuestion(BaseQuestion):
    """Matching headings question type."""
    type: Literal["matching_headings"] = "matching_headings"
    passage_reference: str
    heading_options: List[str]
    answer: str


class MatchingFeaturesQuestion(BaseQuestion):
    """Matching features question type."""
    type: Literal["matching_features"] = "matching_features"
    statement: str
    feature_options: List[str]
    answer: str


class MatchingInformationQuestion(BaseQuestion):
    """Matching information question type."""
    type: Literal["matching_information"] = "matching_information"
    question_text: Optional[str] = None
    statement: Optional[str] = None
    options: Optional[List[str]] = None
    answer: str


# Union type for all question types
ReadingQuestion = Union[
    MultipleChoiceQuestion,
    IdentifyingInformationQuestion,
    IdentifyingWriterViewQuestion,
    ShortAnswerQuestion,
    SentenceCompletionQuestion,
    SummaryCompletionQuestion,
    MatchingHeadingsQuestion,
    MatchingFeaturesQuestion,
    MatchingInformationQuestion,
]


# === Passage Schema ===

class ReadingPassage(BaseModel):
    """Schema for a single reading passage."""
    passage_number: int = Field(..., ge=1, le=3)
    heading: str
    text: str = Field(..., min_length=500)
    word_count: int = Field(..., ge=750, le=950)
    topic: Optional[str] = None
    difficulty_band: Optional[str] = None
    lexical_range_descriptor: Optional[str] = None
    grammatical_complexity: Optional[str] = None
    questions: List[Dict[str, Any]]  # Using Dict for flexibility with various question types


# === Test Metadata ===

class ReadingTestMetadata(BaseModel):
    """Metadata for the reading test."""
    schema_version: str = "2.0"
    generated_at: str
    difficulty_band: str = Field(
        ..., 
        pattern=r"^(5\.0|5\.5|6\.0|6\.5|7\.0|7\.5|8\.0|8\.5|9\.0)$"
    )
    test_source: Optional[str] = None
    passage_sources: Optional[List[str]] = None


# === Complete Test Schema ===

class IELTSReadingTest(BaseModel):
    """Complete IELTS Reading Test schema matching frontend expectations."""
    test_type: Literal["IELTS Academic", "IELTS General Training"]
    passages: List[ReadingPassage] = Field(..., min_length=3, max_length=3)
    total_questions: int = Field(default=40, const=True)
    total_duration_minutes: int = Field(default=60, const=True)
    test_metadata: ReadingTestMetadata
    answer_key: Dict[str, Union[str, int, List[str]]]

    class Config:
        json_schema_extra = {
            "example": {
                "test_type": "IELTS Academic",
                "total_questions": 40,
                "total_duration_minutes": 60,
                "test_metadata": {
                    "schema_version": "2.0",
                    "generated_at": "2026-02-24T10:00:00",
                    "difficulty_band": "7.0",
                    "test_source": "AI Generated Practice Test"
                },
                "passages": [],
                "answer_key": {}
            }
        }
