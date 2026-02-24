"""
IELTS Writing Test Generation Service.
Wraps the existing Gemini-based writing test generation logic.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Literal, Optional

from core.gemini_client import GeminiClient, get_gemini_client
from core.exceptions import SchemaValidationError
from services.base import BaseIELTSService

# Configure logger with detailed format
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class WritingTestService(BaseIELTSService):
    """Service for generating IELTS Writing tests using Gemini API."""
    
    # Valid difficulty bands
    VALID_BANDS = ["5.0", "5.5", "6.0", "6.5", "7.0", "7.5", "8.0", "8.5", "9.0"]
    
    # Valid modules
    VALID_MODULES = ["Academic", "General Training"]
    
    def __init__(self, gemini_client: Optional[GeminiClient] = None):
        self.gemini_client = gemini_client or get_gemini_client()
        logger.info("WritingTestService initialized")
    
    def validate_schema(self, data: Dict[str, Any], module: str = "Academic") -> bool:
        """
        Validate test data against IELTS Writing schema v3.0 specification.
        
        Args:
            data: Generated test data to validate.
            module: Expected module type.
            
        Returns:
            True if validation passes.
            
        Raises:
            SchemaValidationError: If validation fails.
        """
        logger.info(f"Starting schema validation for writing test, module={module}")
        logger.debug(f"Data keys received: {list(data.keys())}")
        errors = []
        warnings = []
        
        # Check required top-level keys
        required_keys = {"test_name", "module", "total_time_minutes", "tasks", "assessment", "test_metadata"}
        missing_keys = required_keys - set(data.keys())
        if missing_keys:
            errors.append(f"Missing required keys: {missing_keys}")
        
        # Validate test name
        if data.get("test_name") != "IELTS Writing":
            errors.append(f"Invalid test_name: {data.get('test_name')}")
        
        # Validate module
        if data.get("module") != module:
            errors.append(f"Invalid module: expected {module}, got {data.get('module')}")
        
        # Validate duration
        if data.get("total_time_minutes") != 60:
            errors.append(f"Invalid duration: must be 60 minutes, got {data.get('total_time_minutes')}")
        
        # Validate recommended time split if present
        if "recommended_time_split" in data:
            time_split = data["recommended_time_split"]
            if time_split.get("task_1_minutes") != 20 or time_split.get("task_2_minutes") != 40:
                warnings.append("Non-standard time split recommended")
        
        # Validate tasks
        tasks = data.get("tasks", [])
        if len(tasks) != 2:
            errors.append(f"Must have exactly 2 tasks, got {len(tasks)}")
        else:
            # Validate Task 1
            task_1 = tasks[0]
            if task_1.get("task_number") != 1:
                errors.append("Task 1 number mismatch")
            if task_1.get("minimum_word_count") != 150:
                errors.append(f"Task 1 minimum word count must be 150, got {task_1.get('minimum_word_count')}")
            if task_1.get("assessment_weight") != "33%":
                warnings.append("Task 1 assessment weight should be 33%")
            
            # Validate Task 1 type based on module
            task_1_type = task_1.get("task_type", "")
            if module == "Academic":
                if not task_1_type.startswith("Report_"):
                    warnings.append("Academic Task 1 should be a Report type")
            elif module == "General Training":
                if not task_1_type.startswith("Letter_"):
                    warnings.append("General Training Task 1 should be a Letter type")
            
            # Validate Task 1 sample responses
            samples_1 = task_1.get("sample_responses", [])
            if len(samples_1) < 1:
                warnings.append("Task 1 has no sample responses")
            else:
                for i, sample in enumerate(samples_1):
                    if "band_score" not in sample:
                        warnings.append(f"Task 1 sample {i+1} missing band_score")
                    if "response_text" not in sample:
                        warnings.append(f"Task 1 sample {i+1} missing response_text")
                    elif len(sample.get("response_text", "")) < 50:
                        warnings.append(f"Task 1 sample {i+1} response is too short")
            
            # Validate Task 2
            task_2 = tasks[1]
            if task_2.get("task_number") != 2:
                errors.append("Task 2 number mismatch")
            if task_2.get("minimum_word_count") != 250:
                errors.append(f"Task 2 minimum word count must be 250, got {task_2.get('minimum_word_count')}")
            if task_2.get("assessment_weight") != "67%":
                warnings.append("Task 2 assessment weight should be 67%")
            
            # Validate Task 2 type
            task_2_type = task_2.get("task_type", "")
            if not task_2_type.startswith("Essay_"):
                warnings.append("Task 2 should be an Essay type")
            
            # Validate Task 2 sample responses
            samples_2 = task_2.get("sample_responses", [])
            if len(samples_2) < 1:
                warnings.append("Task 2 has no sample responses")
        
        # Validate metadata
        metadata = data.get("test_metadata", {})
        if metadata.get("schema_version") != "3.0":
            errors.append(f"Wrong schema version: {metadata.get('schema_version')}, expected 3.0")
        
        if metadata.get("difficulty_band") not in self.VALID_BANDS:
            errors.append(f"Invalid difficulty_band: {metadata.get('difficulty_band')}")
        
        # Validate assessment
        assessment = data.get("assessment", {})
        if "criteria" not in assessment:
            errors.append("Assessment missing criteria")
        if "scoring_methodology" not in assessment:
            errors.append("Assessment missing scoring_methodology")
        if "band_scale" not in assessment:
            errors.append("Assessment missing band_scale")
        
        if errors:
            logger.error(f"Schema validation failed with {len(errors)} errors: {errors}")
            if warnings:
                logger.warning(f"Schema validation warnings: {warnings}")
            raise SchemaValidationError(
                message="Schema validation failed",
                details={"errors": errors, "warnings": warnings}
            )
        
        if warnings:
            logger.warning(f"Schema validation passed with warnings: {warnings}")
        else:
            logger.info("Schema validation passed successfully")
        
        return True
    
    def _build_prompt(self, module: str, difficulty: str) -> str:
        """Build the Gemini prompt for writing test generation."""
        
        # Define task specifications based on module
        if module == "Academic":
            task_1_spec = """Task 1 (Academic Report):
- Type: Describe a chart, graph, diagram, or process
- Possible visuals: Line Graph, Bar Chart, Pie Chart, Table, Process Diagram, Map, Mixed Chart
- Format: Objective, formal language describing trends/relationships
- Minimum: 150 words"""
            task_1_type = "Report_Chart"
        else:  # General Training
            task_1_spec = """Task 1 (General Training Letter):
- Type: Write a formal, semi-formal, or informal letter
- Purposes: Request, Complaint, Apology, Recommendation, Enquiry, Application, Invitation
- Format: Must match the appropriate register for recipient and situation
- Minimum: 150 words"""
            task_1_type = "Letter_Formal"
        
        task_2_spec = """Task 2 (Essay - Both Modules):
- Type: Write a formal essay
- Essay types: Opinion, Discussion, Problem and Solution, Advantages and Disadvantages
- Format: Clear thesis, supporting paragraphs with examples, formal conclusion
- Minimum: 250 words"""
        
        return f"""You are an expert IELTS Writing examiner. Generate a complete IELTS {module} Writing test following OFFICIAL schema v3.0 specification.

CRITICAL REQUIREMENTS:
1. Module: {module}
2. Difficulty band: {difficulty}
3. Total duration: 60 minutes
4. Exactly 2 tasks with sample responses at 3 different band levels (8, 6, 4)
5. Task weighting: Task 1 (33%), Task 2 (67%)
6. Assessment criteria: Task Achievement/Response, Coherence & Cohesion, Lexical Resource, Grammatical Range & Accuracy
7. Sample responses must be 100+ words minimum and realistic

{task_1_spec}

{task_2_spec}

IMPORTANT SCHEMA REQUIREMENTS FOR SAMPLE RESPONSES:
- Each response must have: band_score, word_count, response_text (100+ words), examiner_commentary, assessment_breakdown
- Assessment breakdown must include all 4 criteria with band-level feedback
- Provide 3 samples per task at bands 8, 6, and 4
- All fields must be strings (no abbreviations in assessment_breakdown)

RETURN ONLY VALID JSON (schema v3.0):
{{
  "test_name": "IELTS Writing",
  "module": "{module}",
  "total_time_minutes": 60,
  "recommended_time_split": {{
    "task_1_minutes": 20,
    "task_2_minutes": 40
  }},
  "test_metadata": {{
    "schema_version": "3.0",
    "generated_at": "{datetime.now().isoformat()}",
    "difficulty_band": "{difficulty}",
    "test_source": "AI Generated Practice Test"
  }},
  "tasks": [
    {{
      "task_number": 1,
      "task_type": "{task_1_type}",
      "module_specific": "{module}",
      "minimum_word_count": 150,
      "recommended_word_count": 165,
      "assessment_weight": "33%",
      "instructions": "You should spend about 20 minutes on this task. Write at least 150 words.",
      "task_context": "You are required to describe visual information in formal, objective language.",
      "prompt": {{
        "task_instruction": "You should spend about 20 minutes on this task.",
        "context_information": "A chart/diagram/map is provided below.",
        {'"visual_data": {"chart_type": "Bar Chart", "title": "Sample Chart Title", "description_text": "Description of the chart data", "time_period": "2015-2025", "units": "Appropriate units"}' if module == "Academic" else '"letter_context": {"situation": "Describe the situation", "purpose": "Complaint", "recipient_type": "Organization", "formality_level": "Formal", "bullet_points": ["Point 1", "Point 2", "Point 3"]}'}
      }},
      "sample_responses": [
        {{
          "band_score": 8,
          "word_count": 168,
          "response_text": "[Full response text 150+ words for band 8]",
          "examiner_commentary": "Commentary on the response",
          "assessment_breakdown": {{
            "task_achievement_or_response": "Band 8: [Detailed feedback]",
            "coherence_and_cohesion": "Band 8: [Detailed feedback]",
            "lexical_resource": "Band 8: [Detailed feedback]",
            "grammatical_range_and_accuracy": "Band 8: [Detailed feedback]"
          }}
        }},
        {{
          "band_score": 6,
          "word_count": 155,
          "response_text": "[Full response text for band 6]",
          "examiner_commentary": "Commentary",
          "assessment_breakdown": {{
            "task_achievement_or_response": "Band 6: [Feedback]",
            "coherence_and_cohesion": "Band 6: [Feedback]",
            "lexical_resource": "Band 6: [Feedback]",
            "grammatical_range_and_accuracy": "Band 6: [Feedback]"
          }}
        }},
        {{
          "band_score": 4,
          "word_count": 145,
          "response_text": "[Full response text for band 4]",
          "examiner_commentary": "Commentary",
          "assessment_breakdown": {{
            "task_achievement_or_response": "Band 4: [Feedback]",
            "coherence_and_cohesion": "Band 4: [Feedback]",
            "lexical_resource": "Band 4: [Feedback]",
            "grammatical_range_and_accuracy": "Band 4: [Feedback]"
          }}
        }}
      ]
    }},
    {{
      "task_number": 2,
      "task_type": "Essay_Opinion",
      "module_specific": "{module}",
      "minimum_word_count": 250,
      "recommended_word_count": 280,
      "assessment_weight": "67%",
      "instructions": "Write an essay of at least 250 words.",
      "task_context": "Respond to a point of view with a well-developed essay.",
      "prompt": {{
        "task_instruction": "Write an essay responding to the following prompt.",
        "context_information": "Present your own ideas and supporting evidence.",
        "essay_context": {{
          "topic": "Topic Title",
          "essay_type": "Opinion",
          "question_prompt": "Full essay question prompt",
          "key_topics": ["Topic 1", "Topic 2", "Topic 3"]
        }}
      }},
      "sample_responses": [
        {{
          "band_score": 8,
          "word_count": 289,
          "response_text": "[Full essay 250+ words for band 8]",
          "examiner_commentary": "Commentary",
          "assessment_breakdown": {{
            "task_achievement_or_response": "Band 8: [Feedback]",
            "coherence_and_cohesion": "Band 8: [Feedback]",
            "lexical_resource": "Band 8: [Feedback]",
            "grammatical_range_and_accuracy": "Band 8: [Feedback]"
          }}
        }},
        {{
          "band_score": 6,
          "word_count": 261,
          "response_text": "[Full essay for band 6]",
          "examiner_commentary": "Commentary",
          "assessment_breakdown": {{
            "task_achievement_or_response": "Band 6: [Feedback]",
            "coherence_and_cohesion": "Band 6: [Feedback]",
            "lexical_resource": "Band 6: [Feedback]",
            "grammatical_range_and_accuracy": "Band 6: [Feedback]"
          }}
        }},
        {{
          "band_score": 4,
          "word_count": 254,
          "response_text": "[Full essay for band 4]",
          "examiner_commentary": "Commentary",
          "assessment_breakdown": {{
            "task_achievement_or_response": "Band 4: [Feedback]",
            "coherence_and_cohesion": "Band 4: [Feedback]",
            "lexical_resource": "Band 4: [Feedback]",
            "grammatical_range_and_accuracy": "Band 4: [Feedback]"
          }}
        }}
      ]
    }}
  ],
  "assessment": {{
    "criteria": [
      "Task Achievement (Task 1) / Task Response (Task 2)",
      "Coherence and Cohesion",
      "Lexical Resource",
      "Grammatical Range and Accuracy"
    ],
    "scoring_methodology": {{
      "description": "Each criterion scored independently on 0-9 band scale. Task 2 carries more weight (67%) than Task 1 (33%).",
      "task_weighting": {{
        "task_1_weight": "33%",
        "task_2_weight": "67%"
      }},
      "criterion_weighting": "All criteria equally weighted (25% each)"
    }},
    "band_scale": [
      {{"band": 9, "skill_level": "Expert", "descriptor": "Fully operational command"}},
      {{"band": 8, "skill_level": "Very Good", "descriptor": "Fully operational with occasional inaccuracies"}},
      {{"band": 7, "skill_level": "Good", "descriptor": "Operational command with occasional inaccuracies"}},
      {{"band": 6, "skill_level": "Competent", "descriptor": "Effective command despite some inaccuracies"}},
      {{"band": 5, "skill_level": "Modest", "descriptor": "Partial command"}},
      {{"band": 4, "skill_level": "Limited", "descriptor": "Basic competence limited to familiar situations"}},
      {{"band": 3, "skill_level": "Extremely Limited", "descriptor": "Very basic information only"}}
    ],
    "detailed_rubrics": {{
      "Task Achievement (Task 1)": {{
        "band_9": "Fully addresses all parts with excellent coverage",
        "band_8": "Addresses all parts adequately",
        "band_7": "Addresses task adequately with overview",
        "band_6": "Addresses task with key information covered",
        "band_5": "Attempts to address task with some key information"
      }},
      "Task Response (Task 2)": {{
        "band_9": "Fully addresses prompt with fully developed position",
        "band_8": "Addresses all parts with well-developed position",
        "band_7": "Addresses prompt with clear position",
        "band_6": "Addresses prompt with position presented",
        "band_5": "Addresses prompt to some extent"
      }},
      "Coherence and Cohesion": {{
        "band_9": "Logical organization with excellent cohesive devices",
        "band_8": "Logical organization with good cohesive devices",
        "band_7": "Coherent arrangement with range of devices",
        "band_6": "Coherent arrangement with some devices",
        "band_5": "Some organization with basic devices"
      }},
      "Lexical Resource": {{
        "band_9": "Sophisticated vocabulary used naturally",
        "band_8": "Wide range used accurately",
        "band_7": "Range used accurately and appropriately",
        "band_6": "Adequate vocabulary to convey meaning",
        "band_5": "Limited range with some inaccuracy"
      }},
      "Grammatical Range and Accuracy": {{
        "band_9": "Wide range of structures used accurately",
        "band_8": "Wide range with most sentences well-formed",
        "band_7": "Range of structures accurately used",
        "band_6": "Variety of structures, generally accurate",
        "band_5": "Some range with inaccuracy"
      }}
    }}
  }}
}}

Generate the complete test NOW with FULL sample responses (not placeholders). Return ONLY valid JSON:"""
    
    async def generate_test(
        self,
        module: Literal["Academic", "General Training"] = "Academic",
        difficulty: str = "7.0"
    ) -> Dict[str, Any]:
        """
        Generate a complete IELTS Writing test.
        
        Args:
            module: "Academic" or "General Training"
            difficulty: IELTS band level (5.0-9.0 with 0.5 increments)
            
        Returns:
            Dictionary with full IELTS Writing test (2 tasks with sample responses)
            
        Raises:
            GeminiAPIError: If Gemini API call fails.
            JSONParseError: If response cannot be parsed as JSON.
            SchemaValidationError: If generated data fails validation.
        """
        logger.info(f"Starting writing test generation with module={module}, difficulty={difficulty}")
        
        # Validate module
        if module not in self.VALID_MODULES:
            logger.error(f"Invalid module requested: {module}")
            raise SchemaValidationError(
                message=f"Invalid module: {module}",
                details={"valid_modules": self.VALID_MODULES}
            )
        
        # Validate difficulty
        if difficulty not in self.VALID_BANDS:
            logger.error(f"Invalid difficulty band requested: {difficulty}")
            raise SchemaValidationError(
                message=f"Invalid difficulty band: {difficulty}",
                details={"valid_bands": self.VALID_BANDS}
            )
        
        # Build prompt
        prompt = self._build_prompt(module, difficulty)
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
        
        # Normalize data for frontend compatibility
        logger.info("Normalizing data for frontend compatibility...")
        test_data = self._normalize_for_frontend(test_data)
        
        # Validate against schema
        logger.info("Validating against schema...")
        self.validate_schema(test_data, module)
        
        logger.info("Successfully generated writing test")
        logger.info(f"Test contains {len(test_data.get('tasks', []))} tasks")
        for i, task in enumerate(test_data.get('tasks', []), 1):
            logger.info(f"  Task {i}: type={task.get('task_type')}, samples={len(task.get('sample_responses', []))}")
        
        return test_data
    
    def _normalize_for_frontend(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalize the data structure to match frontend expectations.
        
        The frontend (testDataService.ts) expects:
        - tasks[].task_number
        - tasks[].task_type
        - tasks[].instructions
        - tasks[].prompt.task_instruction
        - tasks[].prompt.context_information
        - tasks[].prompt.visual_data (for Academic Task 1)
        - tasks[].prompt.letter_context (for General Training Task 1)
        - tasks[].prompt.essay_context (for Task 2)
        - tasks[].sample_responses[]
        
        Args:
            data: The parsed test data
            
        Returns:
            Normalized test data
        """
        logger.info("Normalizing writing test data for frontend")
        tasks = data.get("tasks", [])
        
        for task_idx, task in enumerate(tasks, 1):
            task_num = task.get("task_number", task_idx)
            task_type = task.get("task_type", "unknown")
            logger.debug(f"Processing task {task_num} ({task_type})")
            
            # Ensure prompt structure exists
            if "prompt" not in task:
                task["prompt"] = {}
                logger.warning(f"Task {task_num}: No prompt found, initialized empty")
            
            prompt = task["prompt"]
            
            # Ensure task_instruction exists
            if "task_instruction" not in prompt:
                prompt["task_instruction"] = task.get("instructions", "Complete this task.")
                logger.debug(f"Task {task_num}: Copied instructions to prompt.task_instruction")
            
            # Ensure context_information exists
            if "context_information" not in prompt:
                prompt["context_information"] = task.get("task_context", "")
                logger.debug(f"Task {task_num}: Set context_information from task_context")
            
            # For Task 1 Academic: ensure visual_data exists
            if task_num == 1 and task_type and task_type.startswith("Report_"):
                if "visual_data" not in prompt:
                    prompt["visual_data"] = {
                        "chart_type": "Mixed Chart",
                        "description_text": prompt.get("context_information", "Describe the data shown."),
                        "title": "Visual Data"
                    }
                    logger.debug(f"Task {task_num}: Created default visual_data structure")
            
            # For Task 1 General Training: ensure letter_context exists
            if task_num == 1 and task_type and task_type.startswith("Letter_"):
                if "letter_context" not in prompt:
                    prompt["letter_context"] = {
                        "situation": prompt.get("context_information", "Write a letter."),
                        "purpose": "General",
                        "formality_level": "Formal"
                    }
                    logger.debug(f"Task {task_num}: Created default letter_context structure")
            
            # For Task 2: ensure essay_context exists
            if task_num == 2 or (task_type and task_type.startswith("Essay_")):
                if "essay_context" not in prompt:
                    prompt["essay_context"] = {
                        "topic": "Essay Topic",
                        "essay_type": task_type.replace("Essay_", "") if task_type else "Opinion",
                        "question_prompt": prompt.get("context_information", "Write an essay.")
                    }
                    logger.debug(f"Task {task_num}: Created default essay_context structure")
            
            # Ensure sample_responses is an array
            if "sample_responses" not in task:
                task["sample_responses"] = []
                logger.warning(f"Task {task_num}: No sample_responses found, initialized empty")
            
            # Log task structure
            logger.debug(f"Task {task_num}: prompt keys={list(prompt.keys())}, samples={len(task.get('sample_responses', []))}")
        
        logger.info("Frontend normalization complete for writing test")
        return data


def get_writing_service() -> WritingTestService:
    """Dependency injection for writing test service."""
    return WritingTestService()
