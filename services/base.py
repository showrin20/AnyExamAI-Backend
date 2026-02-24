"""
Base service class with common functionality.
"""

import json
import logging
import re
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from core.exceptions import JSONParseError

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class BaseIELTSService(ABC):
    """Abstract base class for IELTS test generation services."""
    
    @abstractmethod
    async def generate_test(self, **kwargs) -> Dict[str, Any]:
        """Generate an IELTS test. Must be implemented by subclasses."""
        pass
    
    @abstractmethod
    def validate_schema(self, data: Dict[str, Any]) -> bool:
        """Validate the generated data against the schema."""
        pass
    
    def extract_json_from_response(self, response_text: str) -> Optional[Dict[str, Any]]:
        """
        Extract and parse JSON from model response with multiple fallback strategies.
        
        Args:
            response_text: Raw text response from Gemini API.
            
        Returns:
            Parsed JSON dictionary or None if parsing fails.
            
        Raises:
            JSONParseError: If all parsing strategies fail.
        """
        logger.info("Starting JSON extraction from response")
        logger.debug(f"Response length: {len(response_text)} characters")
        
        # Clean up the response text
        cleaned_text = response_text.strip()
        
        # Strategy 1: Remove markdown code block markers first
        if cleaned_text.startswith('```'):
            logger.debug("Strategy 1: Removing markdown code block markers")
            # Remove opening ```json or ```
            cleaned_text = re.sub(r'^```(?:json)?\s*\n?', '', cleaned_text)
            # Remove closing ```
            cleaned_text = re.sub(r'\n?```\s*$', '', cleaned_text)
        
        # Strategy 2: Direct JSON parsing on cleaned text
        try:
            logger.debug("Strategy 2: Attempting direct JSON parse")
            result = json.loads(cleaned_text)
            logger.info("Successfully parsed JSON using Strategy 2 (direct parse)")
            return result
        except json.JSONDecodeError as e:
            logger.debug(f"Strategy 2 failed: {e}")
            pass
        
        # Strategy 3: Find the outermost JSON object { ... }
        logger.debug("Strategy 3: Finding outermost JSON object")
        start_idx = cleaned_text.find('{')
        if start_idx != -1:
            brace_count = 0
            end_idx = start_idx
            for i, char in enumerate(cleaned_text[start_idx:], start_idx):
                if char == '{':
                    brace_count += 1
                elif char == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        end_idx = i
                        break
            
            if brace_count == 0:
                json_str = cleaned_text[start_idx:end_idx + 1]
                logger.debug(f"Found JSON object from index {start_idx} to {end_idx}")
                try:
                    result = json.loads(json_str)
                    logger.info("Successfully parsed JSON using Strategy 3 (brace matching)")
                    return result
                except json.JSONDecodeError as e:
                    logger.debug(f"Strategy 3 failed: {e}")
                    pass
        
        # Strategy 4: Try original text with markdown code block pattern
        logger.debug("Strategy 4: Trying markdown code block regex")
        code_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)\s*```', response_text)
        if code_block_match:
            try:
                result = json.loads(code_block_match.group(1))
                logger.info("Successfully parsed JSON using Strategy 4 (markdown code block)")
                return result
            except json.JSONDecodeError as e:
                logger.debug(f"Strategy 4 failed: {e}")
                pass
        
        # Strategy 5: Extract JSON block with regex
        logger.debug("Strategy 5: Extracting JSON with regex")
        json_match = re.search(r'\{[\s\S]*\}', response_text)
        if json_match:
            try:
                result = json.loads(json_match.group(0))
                logger.info("Successfully parsed JSON using Strategy 5 (regex extraction)")
                return result
            except json.JSONDecodeError as e:
                logger.debug(f"Strategy 5 failed: {e}")
                pass
        
        logger.error("All JSON extraction strategies failed")
        logger.error(f"Response preview: {response_text[:500]}")
        raise JSONParseError(
            message="Could not extract valid JSON from API response",
            details={"response_preview": response_text[:500] if len(response_text) > 500 else response_text}
        )
