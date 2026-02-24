"""
IELTS Reading Test Generation Service.
Wraps the existing Gemini-based reading test generation logic.
"""

import asyncio
import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

from core.gemini_client import GeminiClient, get_gemini_client
from core.exceptions import SchemaValidationError, GeminiAPIError
from services.base import BaseIELTSService

# Configure logger with detailed format
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class ReadingTestService(BaseIELTSService):
    """Service for generating IELTS Reading tests using Gemini API."""
    
    # Valid difficulty bands
    VALID_BANDS = ["5.0", "5.5", "6.0", "6.5", "7.0", "7.5", "8.0", "8.5", "9.0"]
    
    # Retry configuration
    MAX_RETRIES = 3
    RETRY_DELAY_SECONDS = 2
    
    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        self.gemini_client = gemini_client or get_gemini_client()
        logger.info("ReadingTestService initialized")
    
    def validate_schema(self, data: Dict[str, Any]) -> bool:
        """
        Validate test data against official IELTS Reading schema v2.0 specification.
        
        Args:
            data: Generated test data to validate.
            
        Returns:
            True if validation passes.
            
        Raises:
            SchemaValidationError: If validation fails.
        """
        logger.info("Starting schema validation for reading test")
        logger.debug(f"Data keys received: {list(data.keys())}")
        errors = []
        
        # Check required top-level keys
        required_keys = {"test_type", "passages", "total_questions", "total_duration_minutes", "test_metadata"}
        missing_keys = required_keys - set(data.keys())
        if missing_keys:
            errors.append(f"Missing required keys: {missing_keys}")
        
        # Validate test type
        if data.get("test_type") not in ["IELTS Academic", "IELTS General Training"]:
            errors.append(f"Invalid test_type: {data.get('test_type')}")
        
        # Validate total questions
        if data.get("total_questions") != 40:
            errors.append(f"Invalid total_questions: must be 40, got {data.get('total_questions')}")
        
        # Validate duration
        if data.get("total_duration_minutes") != 60:
            errors.append(f"Invalid duration: must be 60 minutes, got {data.get('total_duration_minutes')}")
        
        # Validate passages
        passages = data.get("passages", [])
        if len(passages) != 3:
            errors.append(f"Must have exactly 3 passages, got {len(passages)}")
        
        total_q = 0
        for i, passage in enumerate(passages, 1):
            req_p_keys = {"passage_number", "heading", "text", "word_count", "questions"}
            missing_p_keys = req_p_keys - set(passage.keys())
            if missing_p_keys:
                errors.append(f"Passage {i} missing keys: {missing_p_keys}")
            
            if passage.get("passage_number") != i:
                errors.append(f"Passage number mismatch: expected {i}, got {passage.get('passage_number')}")
            
            # Word count validation (relaxed range for generated content)
            wc = passage.get("word_count", 0)
            if not (500 <= wc <= 1200):  # More relaxed range for generated content
                errors.append(f"Passage {i} word count {wc} outside acceptable range (500-1200)")
            
            questions = passage.get("questions", [])
            total_q += len(questions)
            
            # Validate each question
            for q in questions:
                req_q_keys = {"question_number", "type", "answer"}
                missing_q_keys = req_q_keys - set(q.keys())
                if missing_q_keys:
                    errors.append(f"Question {q.get('question_number', '?')} missing keys: {missing_q_keys}")
        
        # Validate total questions
        if total_q != 40:
            errors.append(f"Total questions across passages: {total_q}, expected 40")
        
        # Validate metadata
        metadata = data.get("test_metadata", {})
        logger.debug(f"Validating metadata: schema_version={metadata.get('schema_version')}, difficulty_band={metadata.get('difficulty_band')}")
        if metadata.get("schema_version") != "2.0":
            errors.append(f"Wrong schema version: {metadata.get('schema_version')}")
        
        if metadata.get("difficulty_band") not in self.VALID_BANDS:
            errors.append(f"Invalid difficulty_band: {metadata.get('difficulty_band')}")
        
        # Validate topics exist in metadata
        if "topics" not in metadata or not isinstance(metadata.get("topics"), list) or len(metadata.get("topics", [])) != 3:
            errors.append("test_metadata must contain 'topics' array with exactly 3 topics")
        
        # Validate answer key
        answer_key = data.get("answer_key", {})
        logger.debug(f"Answer key has {len(answer_key)} entries")
        if len(answer_key) != 40:
            errors.append(f"Answer key has {len(answer_key)} entries, expected 40")
        
        if errors:
            logger.error(f"Schema validation failed with {len(errors)} errors: {errors}")
            raise SchemaValidationError(
                message="Schema validation failed",
                details={"errors": errors}
            )
        
        logger.info("Schema validation passed successfully")
        return True
    
    def _build_prompt(
        self,
        difficulty: str,
        passage_difficulties: List[str],
        exclude_topics: List[str] = None
    ) -> str:
        """Build the Gemini prompt for reading test generation with auto-selected topics."""
        
        exclude_section = ""
        if exclude_topics and len(exclude_topics) > 0:
            # Only show last 50 topics to keep prompt reasonable
            recent_excluded = exclude_topics[-50:] if len(exclude_topics) > 50 else exclude_topics
            exclude_section = f"""
TOPICS TO AVOID (previously used - DO NOT use these or very similar topics):
{', '.join(recent_excluded)}

"""
        
        return f"""You are an IELTS Academic Reading test expert. Generate a COMPLETE IELTS Academic Reading test.

TOPIC SELECTION:
- YOU must select 3 diverse, interesting, and academically appropriate topics
- Topics should be from different fields (e.g., science, history, social sciences, technology, arts, environment)
- Choose topics that would genuinely appear in IELTS Academic tests
{exclude_section}
CRITICAL REQUIREMENTS:
1. Exactly 3 passages with YOUR SELECTED topics
2. EXACTLY 40 INDIVIDUAL questions total (13-14 per passage)
3. Each question MUST have its own unique question_number (1-40, sequential)
4. Each question MUST have an "answer" field
5. Each question MUST have an "explanation" field with ONE concise sentence explaining WHY the answer is correct
6. Passage length: 750-950 words EACH
7. Include selected topics in test_metadata.topics array

STRICT QUESTION FORMAT RULES (FOLLOW EXACTLY):

1. multiple_choice:
{{"question_number": 1, "type": "multiple_choice", "question_text": "What is...?", "options": ["A. First option", "B. Second option", "C. Third option", "D. Fourth option"], "answer": "A", "explanation": "The passage states X in paragraph Y."}}

2. identifying_information (True/False/Not Given):
{{"question_number": 2, "type": "identifying_information", "statement": "Statement to evaluate", "answer": "True", "explanation": "Paragraph X explicitly states that..."}}

3. identifying_writer_view (Yes/No/Not Given):
{{"question_number": 3, "type": "identifying_writer_view", "statement": "Opinion statement", "answer": "Yes", "explanation": "The writer argues in paragraph X that..."}}

4. short_answer:
{{"question_number": 4, "type": "short_answer", "question_text": "What does X refer to?", "max_word_count": 3, "answer": "specific answer", "explanation": "The passage mentions this in paragraph X."}}

5. sentence_completion (with options):
{{"question_number": 5, "type": "sentence_completion", "incomplete_sentence": "The main purpose of X is to ______.", "options": ["A. option one", "B. option two", "C. option three", "D. option four"], "answer": "C", "explanation": "Paragraph X states that..."}}

6. summary_completion (ONE blank per question - EACH BLANK IS A SEPARATE QUESTION):
{{"question_number": 6, "type": "summary_completion", "summary_text": "Research shows that ______ is important.", "answer": "collaboration", "max_word_count": 2, "explanation": "The passage uses this term in paragraph X."}}

7. matching_headings (use passage_reference and heading_options):
{{"question_number": 7, "type": "matching_headings", "passage_reference": "Paragraph A", "heading_options": ["i. First heading", "ii. Second heading", "iii. Third heading", "iv. Fourth heading", "v. Fifth heading", "vi. Sixth heading", "vii. Seventh heading"], "answer": "iii", "explanation": "Paragraph A discusses..."}}

8. matching_features (use statement and feature_options):
{{"question_number": 8, "type": "matching_features", "statement": "Developed the theory of X", "feature_options": ["A. Researcher One", "B. Researcher Two", "C. Researcher Three", "D. Researcher Four"], "answer": "B", "explanation": "The passage attributes this to Researcher Two in paragraph X."}}

CRITICAL RULES:
- EVERY question must be a SEPARATE object with its own question_number
- DO NOT bundle multiple blanks into one question
- Questions 1-13 for Passage 1, 14-26 for Passage 2, 27-40 for Passage 3
- Total must be EXACTLY 40 individual question objects
- EVERY question MUST have "explanation" field
- Include your selected topics in test_metadata.topics array

RETURN ONLY VALID JSON:
{{
  "test_type": "IELTS Academic",
  "total_questions": 40,
  "total_duration_minutes": 60,
  "test_metadata": {{
    "schema_version": "2.0",
    "generated_at": "{datetime.now().isoformat()}",
    "difficulty_band": "{difficulty}",
    "test_source": "AI Generated Practice Test",
    "passage_sources": ["academic_journal", "book", "magazine"],
    "topics": ["Your Selected Topic 1", "Your Selected Topic 2", "Your Selected Topic 3"]
  }},
  "passages": [
    {{
      "passage_number": 1,
      "heading": "Title for your first topic",
      "text": "[FULL 750-950 WORD PASSAGE HERE]",
      "word_count": 850,
      "topic": "Your Selected Topic 1",
      "difficulty_band": "{passage_difficulties[0]}",
      "lexical_range_descriptor": "Academic vocabulary appropriate for band {passage_difficulties[0]}",
      "grammatical_complexity": "Complex sentences with passive voice and multiple clauses",
      "questions": [
        {{"question_number": 1, "type": "multiple_choice", "question_text": "Question?", "options": ["A. opt1", "B. opt2", "C. opt3", "D. opt4"], "answer": "A", "explanation": "Evidence from passage."}},
        {{"question_number": 2, "type": "identifying_information", "statement": "Statement", "answer": "True", "explanation": "Why it's true."}},
        ... (continue to 13 questions)
      ]
    }},
    {{
      "passage_number": 2,
      "heading": "Title for your second topic",
      "text": "[FULL 750-950 WORD PASSAGE HERE]",
      "word_count": 850,
      "topic": "Your Selected Topic 2",
      "difficulty_band": "{passage_difficulties[1]}",
      "questions": [
        {{"question_number": 14, ...}},
        ... (questions 14-26)
      ]
    }},
    {{
      "passage_number": 3,
      "heading": "Title for your third topic",
      "text": "[FULL 750-950 WORD PASSAGE HERE]",
      "word_count": 850,
      "topic": "Your Selected Topic 3",
      "difficulty_band": "{passage_difficulties[2]}",
      "questions": [
        {{"question_number": 27, ...}},
        ... (questions 27-40)
      ]
    }}
  ],
  "answer_key": {{"1": "A", "2": "True", "3": "False", ... (all 40 answers)}}
}}

Generate the COMPLETE test with FULL passage texts (750-950 words each) and ALL 40 individual questions. Return ONLY valid JSON:"""
    
    async def generate_test(
        self,
        difficulty: str = "7.0",
        exclude_topics: List[str] = None
    ) -> Dict[str, Any]:
        """
        Generate a complete IELTS Academic Reading test with retry logic.
        
        Args:
            difficulty: IELTS band level (5.0-9.0 with 0.5 increments)
            exclude_topics: List of topics to exclude (previously used)
            
        Returns:
            Dictionary with full IELTS Academic reading test (3 passages, 40 questions)
            
        Raises:
            GeminiAPIError: If Gemini API call fails.
            JSONParseError: If response cannot be parsed as JSON.
            SchemaValidationError: If generated data fails validation after all retries.
        """
        logger.info(f"Starting reading test generation with difficulty={difficulty}")
        logger.debug(f"Exclude topics count: {len(exclude_topics) if exclude_topics else 0}")
        
        # Validate difficulty
        if difficulty not in self.VALID_BANDS:
            logger.error(f"Invalid difficulty band requested: {difficulty}")
            raise SchemaValidationError(
                message=f"Invalid difficulty band: {difficulty}",
                details={"valid_bands": self.VALID_BANDS}
            )
        
        # Calculate passage difficulty progression
        passage_difficulties = [
            "6.0" if float(difficulty) <= 6.5 else "6.5",
            difficulty,
            "8.0" if float(difficulty) >= 7.5 else "7.5"
        ]
        logger.debug(f"Passage difficulties: {passage_difficulties}")
        
        last_error = None
        all_errors = []
        
        for attempt in range(1, self.MAX_RETRIES + 1):
            try:
                logger.info(f"Generating reading test (attempt {attempt}/{self.MAX_RETRIES})")
                
                # Build prompt with exclude_topics
                prompt = self._build_prompt(difficulty, passage_difficulties, exclude_topics)
                logger.debug(f"Prompt length: {len(prompt)} characters")
                
                # Generate content using Gemini
                logger.info("Sending request to Gemini API...")
                response_text = await self.gemini_client.generate_content(prompt)
                logger.info(f"Received response from Gemini API, length: {len(response_text)} characters")
                logger.debug(f"Response preview: {response_text[:500]}...")
                
                # Parse JSON from response
                logger.info("Parsing JSON from response...")
                test_data = self.extract_json_from_response(response_text)
                logger.info(f"Successfully parsed JSON with keys: {list(test_data.keys())}")
                
                # Attempt to fix common issues before validation
                logger.info("Fixing common issues in generated data...")
                test_data = self._fix_common_issues(test_data)
                
                # Normalize question fields for frontend compatibility
                logger.info("Normalizing question fields for frontend compatibility...")
                test_data = self._normalize_for_frontend(test_data)
                
                # Validate against schema
                logger.info("Validating against schema...")
                self.validate_schema(test_data)
                
                logger.info(f"Successfully generated reading test on attempt {attempt}")
                logger.info(f"Test contains {len(test_data.get('passages', []))} passages")
                for i, passage in enumerate(test_data.get('passages', []), 1):
                    logger.info(f"  Passage {i}: {len(passage.get('questions', []))} questions, {passage.get('word_count', 0)} words")
                
                return test_data
                
            except SchemaValidationError as e:
                last_error = e
                all_errors.append(f"Attempt {attempt}: {e.details.get('errors', [])}")
                logger.warning(f"Schema validation failed on attempt {attempt}: {e.details}")
                
                if attempt < self.MAX_RETRIES:
                    logger.info(f"Retrying in {self.RETRY_DELAY_SECONDS} seconds...")
                    await asyncio.sleep(self.RETRY_DELAY_SECONDS)
                    continue
            except Exception as e:
                last_error = e
                all_errors.append(f"Attempt {attempt}: {str(e)}")
                logger.error(f"Error on attempt {attempt}: {str(e)}", exc_info=True)
                
                if attempt < self.MAX_RETRIES:
                    logger.info(f"Retrying in {self.RETRY_DELAY_SECONDS} seconds...")
                    await asyncio.sleep(self.RETRY_DELAY_SECONDS)
                    continue
        
        # All retries exhausted
        logger.error(f"All {self.MAX_RETRIES} attempts failed")
        logger.error(f"All errors: {all_errors}")
        if isinstance(last_error, SchemaValidationError):
            raise SchemaValidationError(
                message=f"Schema validation failed after {self.MAX_RETRIES} attempts",
                details={"all_errors": all_errors, "last_errors": last_error.details.get("errors", [])}
            )
        raise last_error
    
    def _fix_common_issues(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Attempt to fix common issues in the generated data.
        
        Args:
            data: The parsed test data
            
        Returns:
            Fixed test data
        """
        logger.info("Fixing common issues in generated data")
        passages = data.get("passages", [])
        
        for i, passage in enumerate(passages, 1):
            # Fix missing word_count by counting words in text
            if "word_count" not in passage or passage.get("word_count", 0) == 0:
                text = passage.get("text", "")
                if text:
                    passage["word_count"] = len(text.split())
                    logger.debug(f"Fixed word_count for passage {i}: {passage['word_count']}")
            
            # Ensure questions is a list
            if "questions" not in passage:
                passage["questions"] = []
                logger.warning(f"Passage {i} had no questions array, initialized empty")
        
        # Rebuild answer_key from questions if missing or incomplete
        answer_key = data.get("answer_key", {})
        if len(answer_key) < 40:
            logger.info(f"Answer key incomplete ({len(answer_key)}/40), rebuilding from questions")
            for passage in passages:
                for q in passage.get("questions", []):
                    q_num = str(q.get("question_number", ""))
                    if q_num and "answer" in q:
                        answer_key[q_num] = q["answer"]
            data["answer_key"] = answer_key
            logger.info(f"Rebuilt answer_key with {len(answer_key)} entries")
        
        return data
    
    def _normalize_for_frontend(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize the data structure to match frontend expectations.
        
        The frontend (testDataService.ts) expects:
        - passages[].questions[].question_text OR statement OR incomplete_sentence
        - passages[].questions[].options OR heading_options OR feature_options
        - passages[].questions[].answer
        - passages[].questions[].explanation
        
        Args:
            data: The parsed test data
            
        Returns:
            Normalized test data
        """
        logger.info("Normalizing data for frontend compatibility")
        passages = data.get("passages", [])
        
        for passage_idx, passage in enumerate(passages, 1):
            questions = passage.get("questions", [])
            logger.debug(f"Processing passage {passage_idx} with {len(questions)} questions")
            
            for q in questions:
                q_num = q.get("question_number", "?")
                q_type = q.get("type", "unknown")
                
                # Ensure question has a text field that frontend can use
                # Frontend looks for: question_text, statement, incomplete_sentence, summary_text, passage_reference
                if not any(key in q for key in ["question_text", "statement", "incomplete_sentence", "summary_text", "passage_reference"]):
                    # Try to extract text from other fields
                    if "text" in q:
                        q["question_text"] = q["text"]
                        logger.debug(f"Q{q_num}: Copied 'text' to 'question_text'")
                    elif "prompt" in q:
                        q["question_text"] = q["prompt"]
                        logger.debug(f"Q{q_num}: Copied 'prompt' to 'question_text'")
                
                # Ensure options are available for matching types
                if q_type in ["matching_headings", "matching_features", "matching_information", "matching_sentence_endings"]:
                    # Frontend looks for: heading_options, feature_options, options
                    if "options" in q and not q.get("heading_options") and not q.get("feature_options"):
                        if q_type == "matching_headings":
                            q["heading_options"] = q["options"]
                            logger.debug(f"Q{q_num}: Copied 'options' to 'heading_options'")
                        elif q_type == "matching_features":
                            q["feature_options"] = q["options"]
                            logger.debug(f"Q{q_num}: Copied 'options' to 'feature_options'")
                
                # Ensure explanation field exists
                if "explanation" not in q:
                    q["explanation"] = "Explanation not provided"
                    logger.debug(f"Q{q_num}: Added default explanation")
                
                # Ensure answer field exists
                if "answer" not in q:
                    q["answer"] = ""
                    logger.warning(f"Q{q_num}: No answer field found")
                
                # Log question structure for debugging
                logger.debug(f"Q{q_num} ({q_type}): keys={list(q.keys())}")
        
        logger.info("Frontend normalization complete")
        return data


def get_reading_service() -> ReadingTestService:
    """Dependency injection for reading test service."""
    return ReadingTestService()
