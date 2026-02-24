"""
IELTS Writing Evaluation Service.
Evaluates user-submitted writing responses using Gemini API with IELTS examiner criteria.
"""

import logging
from typing import Any, Dict, Literal, Optional

from pydantic import ValidationError

from core.gemini_client import GeminiClient, get_gemini_client
from core.exceptions import SchemaValidationError, JSONParseError
from services.base import BaseIELTSService
from schemas.writing_evaluation import WritingEvaluation

# Configure logger with detailed format
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class WritingEvaluationService(BaseIELTSService):
    """
    Service for evaluating IELTS Writing responses using Gemini API.
    
    This service acts as a certified IELTS examiner, providing detailed
    band scores and feedback for each of the four assessment criteria.
    """
    
    # Minimum word count threshold
    MINIMUM_WORD_COUNT = 50
    
    # Valid task numbers
    VALID_TASK_NUMBERS = [1, 2]
    
    # Valid modules
    VALID_MODULES = ["Academic", "General Training"]
    
    # Valid difficulty bands
    VALID_BANDS = ["5.0", "5.5", "6.0", "6.5", "7.0", "7.5", "8.0", "8.5", "9.0"]
    
    # Minimum word requirements per task
    TASK_WORD_REQUIREMENTS = {
        1: 150,
        2: 250
    }
    
    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        """
        Initialize the WritingEvaluationService.
        
        Args:
            gemini_client: Optional GeminiClient instance for dependency injection.
                          If not provided, a default client will be created.
        """
        self.gemini_client = gemini_client or get_gemini_client()
        logger.info("WritingEvaluationService initialized")
    
    async def generate_test(self, **kwargs) -> Dict[str, Any]:
        """
        Not implemented for evaluation service.
        Required by BaseIELTSService but not used for evaluation.
        """
        raise NotImplementedError(
            "WritingEvaluationService does not generate tests. Use evaluate_response() instead."
        )
    
    def validate_schema(self, data: Dict[str, Any], task_number: int = 2) -> WritingEvaluation:
        """
        Validate evaluation data against WritingEvaluation Pydantic schema.
        
        Args:
            data: Parsed evaluation data from Gemini response.
            task_number: The task number being evaluated.
            
        Returns:
            Validated WritingEvaluation instance.
            
        Raises:
            SchemaValidationError: If validation fails.
        """
        logger.info(f"Starting schema validation for writing evaluation, task_number={task_number}")
        logger.debug(f"Data keys received: {list(data.keys())}")
        
        # Ensure task_number is set correctly
        if "task_number" not in data:
            data["task_number"] = task_number
        
        try:
            validated = WritingEvaluation.model_validate(data)
            logger.info("Schema validation passed successfully")
            return validated
        except ValidationError as e:
            error_details = []
            for error in e.errors():
                field_path = ".".join(str(loc) for loc in error["loc"])
                error_details.append({
                    "field": field_path,
                    "message": error["msg"],
                    "type": error["type"]
                })
            
            logger.error(f"Schema validation failed with {len(error_details)} errors: {error_details}")
            raise SchemaValidationError(
                message="Evaluation response validation failed",
                details={"errors": error_details, "raw_data": data}
            )
    
    def _count_words(self, text: str) -> int:
        """
        Count words in a text string.
        
        Args:
            text: The text to count words in.
            
        Returns:
            Number of words in the text.
        """
        words = text.strip().split()
        return len(words)
    
    def _validate_input(
        self,
        user_response: str,
        task_number: int,
        module: str,
        difficulty: str
    ) -> int:
        """
        Validate input parameters before evaluation.
        
        Args:
            user_response: The user's written response.
            task_number: Task number (1 or 2).
            module: IELTS module type.
            difficulty: Target difficulty band.
            
        Returns:
            Word count of the response.
            
        Raises:
            SchemaValidationError: If validation fails.
        """
        errors = []
        
        # Validate task number
        if task_number not in self.VALID_TASK_NUMBERS:
            errors.append(f"Invalid task_number: {task_number}. Must be 1 or 2.")
        
        # Validate module
        if module not in self.VALID_MODULES:
            errors.append(f"Invalid module: {module}. Must be 'Academic' or 'General Training'.")
        
        # Validate difficulty
        if difficulty not in self.VALID_BANDS:
            errors.append(f"Invalid difficulty: {difficulty}. Must be between 5.0 and 9.0 (0.5 increments).")
        
        # Count words and validate minimum
        word_count = self._count_words(user_response)
        if word_count < self.MINIMUM_WORD_COUNT:
            errors.append(
                f"Response too short: {word_count} words. "
                f"Minimum required: {self.MINIMUM_WORD_COUNT} words."
            )
        
        if errors:
            logger.error(f"Input validation failed: {errors}")
            raise SchemaValidationError(
                message="Input validation failed",
                details={"errors": errors}
            )
        
        logger.info(f"Input validation passed. Word count: {word_count}")
        return word_count
    
    def _build_evaluation_prompt(
        self,
        user_response: str,
        task_number: int,
        module: str,
        word_count: int,
        task_prompt: Optional[str] = None
    ) -> str:
        """
        Build the evaluation prompt for Gemini API.
        
        Args:
            user_response: The user's written response.
            task_number: Task number (1 or 2).
            module: IELTS module type.
            word_count: Word count of the response.
            task_prompt: Optional original task prompt.
            
        Returns:
            Formatted evaluation prompt string.
        """
        # Define task-specific criteria name
        task_criterion = "Task Achievement" if task_number == 1 else "Task Response"
        
        # Define minimum word requirement
        min_words = self.TASK_WORD_REQUIREMENTS[task_number]
        
        # Build context about the task
        task_context = ""
        if task_number == 1:
            if module == "Academic":
                task_context = """
Task 1 Context (Academic - Report Writing):
- The candidate should describe visual information (chart, graph, table, diagram, map, or process)
- Expected register: Formal, objective, impersonal language (avoid "I think", personal opinions)
- MUST include a clear overview/summary of main trends, differences, or stages
- Should select and report key features, make comparisons where relevant
- Should use appropriate data/figures to support descriptions
- Time allowed: 20 minutes
- Minimum 150 words required (penalty if under)

TASK 1 ACADEMIC SPECIFIC ASSESSMENT:
- Does the response have a clear overview?
- Are key features identified and illustrated?
- Is data accurately described?
- Is appropriate language for describing trends/processes used?
- Are comparisons made where relevant?"""
            else:
                task_context = """
Task 1 Context (General Training - Letter Writing):
- The candidate should write a letter (formal, semi-formal, or informal)
- Must address ALL bullet points given in the task
- Register/tone should match the situation and recipient
- Should have appropriate opening and closing for letter type
- Time allowed: 20 minutes
- Minimum 150 words required (penalty if under)

TASK 1 GT SPECIFIC ASSESSMENT:
- Are all bullet points addressed adequately?
- Is the tone/register appropriate for the situation?
- Is the letter format correct (salutation, closing)?
- Is the purpose of the letter clear?"""
        else:
            task_context = """
Task 2 Context (Both Modules - Essay Writing):
- The candidate should write a formal academic essay
- Must present a clear position/thesis throughout
- Should develop ideas with relevant examples and explanations
- Essay types: Opinion, Discussion, Problem-Solution, Advantages-Disadvantages, or Two-part question
- Time allowed: 40 minutes
- Minimum 250 words required (penalty if under)

TASK 2 SPECIFIC ASSESSMENT:
- Is there a clear position/thesis statement?
- Are ideas fully developed with examples?
- Is the conclusion effective?
- Are both sides addressed (if discussion type)?
- Is the argument logical and convincing?"""
        
        # Include original prompt if provided
        original_prompt_section = ""
        if task_prompt:
            original_prompt_section = f"""
ORIGINAL TASK PROMPT:
{task_prompt}
"""
        
        return f"""You are a certified IELTS examiner with extensive experience evaluating IELTS Writing tests. 
Evaluate the following IELTS {module} Writing Task {task_number} response according to official IELTS assessment criteria.

{task_context}
{original_prompt_section}
CANDIDATE'S RESPONSE:
Word Count: {word_count} words (Minimum required: {min_words} words)

---
{user_response}
---

EVALUATION INSTRUCTIONS:
1. Score EACH of the 4 criteria INDEPENDENTLY on a 0-9 band scale
2. Calculate the overall band as the AVERAGE of all 4 criteria, rounded to the nearest 0.5
3. Provide SPECIFIC feedback that directly references the candidate's response with examples from their writing
4. Be objective and fair, following official IELTS band descriptors
5. Consider that a response under the minimum word count should have {task_criterion} penalized
6. For Task {task_number}, focus on the specific requirements mentioned above

ASSESSMENT CRITERIA FOR TASK {task_number}:
1. {task_criterion} (0-9): {"How well the candidate describes the visual data, includes an overview, and highlights key features" if task_number == 1 and module == "Academic" else "How well the candidate addresses all bullet points with appropriate tone/register" if task_number == 1 else "How well the candidate presents and develops their position with relevant, extended ideas"}
2. Coherence and Cohesion (0-9): Logical organization, paragraphing, and use of cohesive devices
3. Lexical Resource (0-9): Range and accuracy of vocabulary, including {"data description language and academic vocabulary" if task_number == 1 and module == "Academic" else "appropriate register and tone" if task_number == 1 else "topic-specific vocabulary and less common lexical items"}
4. Grammatical Range and Accuracy (0-9): Variety and accuracy of grammatical structures

{task_criterion.upper()} BAND DESCRIPTORS (TASK {task_number}):
- Band 9: Fully satisfies all requirements; {"clear overview, accurate data, well-organized" if task_number == 1 else "fully developed position with well-supported ideas"}
- Band 8: {"Covers all requirements; clear overview; well-organized with only occasional slips" if task_number == 1 else "Presents a well-developed response; some occasional lapses"}
- Band 7: {"Covers requirements; clear overview; logical organization; some detail missing" if task_number == 1 else "Clear position throughout; supports main ideas but may over-generalize"}
- Band 6: {"Addresses requirements; presents overview; some irrelevant detail; generally coherent" if task_number == 1 else "Presents relevant position; conclusions may be unclear or repetitive"}
- Band 5: {"Partially addresses task; may lack overview; limited detail" if task_number == 1 else "Expresses a position but development is limited; may lack conclusions"}
- Band 4 and below: Significantly fails to address task requirements

RETURN ONLY VALID JSON (no explanations, no markdown, no code blocks):
{{
    "task_number": {task_number},
    "overall_band": <float: average of 4 criteria rounded to nearest 0.5>,
    "task_achievement_or_response": {{
        "band": <int: 0-9>,
        "feedback": "<string: specific feedback referencing the response, minimum 50 characters>"
    }},
    "coherence_and_cohesion": {{
        "band": <int: 0-9>,
        "feedback": "<string: specific feedback referencing the response, minimum 50 characters>"
    }},
    "lexical_resource": {{
        "band": <int: 0-9>,
        "feedback": "<string: specific feedback referencing the response, minimum 50 characters>"
    }},
    "grammatical_range_and_accuracy": {{
        "band": <int: 0-9>,
        "feedback": "<string: specific feedback referencing the response, minimum 50 characters>"
    }},
    "strengths": "<string: 2-3 specific strengths observed in the response>",
    "weaknesses": "<string: 2-3 specific weaknesses observed in the response>",
    "improvement_suggestions": "<string: actionable suggestions for improvement>"
}}

Evaluate the response NOW and return ONLY valid JSON:"""
    
    async def evaluate_response(
        self,
        user_response: str,
        task_number: Literal[1, 2],
        module: Literal["Academic", "General Training"] = "Academic",
        difficulty: str = "7.0",
        task_prompt: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Evaluate a user's IELTS Writing response.
        
        Args:
            user_response: The user's written response to evaluate.
            task_number: Task number (1 or 2).
            module: IELTS module type ("Academic" or "General Training").
            difficulty: Target difficulty band for context (5.0-9.0).
            task_prompt: Optional original task prompt for more accurate evaluation.
            
        Returns:
            Dictionary containing validated evaluation results.
            
        Raises:
            SchemaValidationError: If input validation or output validation fails.
            GeminiAPIError: If Gemini API call fails.
            JSONParseError: If response cannot be parsed as JSON.
        """
        logger.info(f"=== Starting Writing Evaluation ===")
        logger.info(f"Task: {task_number}, Module: {module}, Difficulty: {difficulty}")
        
        # Validate input parameters
        word_count = self._validate_input(user_response, task_number, module, difficulty)
        logger.info(f"Word count: {word_count}")
        
        # Build evaluation prompt
        prompt = self._build_evaluation_prompt(
            user_response=user_response,
            task_number=task_number,
            module=module,
            word_count=word_count,
            task_prompt=task_prompt
        )
        logger.debug(f"Prompt length: {len(prompt)} characters")
        
        # Call Gemini API
        logger.info("Sending evaluation request to Gemini API...")
        response_text = await self.gemini_client.generate_content(prompt)
        logger.info(f"Received response from Gemini API, length: {len(response_text)} characters")
        logger.debug(f"Response preview: {response_text[:500]}...")
        
        # Extract JSON from response
        logger.info("Extracting JSON from response...")
        try:
            evaluation_data = self.extract_json_from_response(response_text)
            logger.info(f"Successfully parsed JSON with keys: {list(evaluation_data.keys())}")
        except JSONParseError as e:
            logger.error(f"Failed to parse JSON from response: {e.message}")
            raise
        
        # Validate against schema
        logger.info("Validating evaluation against schema...")
        validated_evaluation = self.validate_schema(evaluation_data, task_number)
        
        logger.info("=== Evaluation Complete ===")
        logger.info(f"Overall Band: {validated_evaluation.overall_band}")
        logger.info(f"Task Achievement/Response: {validated_evaluation.task_achievement_or_response.band}")
        logger.info(f"Coherence & Cohesion: {validated_evaluation.coherence_and_cohesion.band}")
        logger.info(f"Lexical Resource: {validated_evaluation.lexical_resource.band}")
        logger.info(f"Grammar: {validated_evaluation.grammatical_range_and_accuracy.band}")
        
        # Return validated data as dictionary
        return validated_evaluation.model_dump()


def get_writing_evaluation_service() -> WritingEvaluationService:
    """Dependency injection for writing evaluation service."""
    return WritingEvaluationService()
