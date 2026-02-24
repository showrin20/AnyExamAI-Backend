"""
Gemini API client wrapper with singleton pattern.
"""

import logging
from typing import Optional
import google.generativeai as genai

from core.config import get_settings
from core.exceptions import GeminiAPIError, ConfigurationError

# Configure logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class GeminiClient:
    """Singleton wrapper for Gemini API client."""
    
    _instance: Optional["GeminiClient"] = None
    _initialized: bool = False
    
    def __new__(cls) -> "GeminiClient":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not GeminiClient._initialized:
            self._configure()
            GeminiClient._initialized = True
    
    def _configure(self) -> None:
        """Configure Gemini API with API key from settings."""
        settings = get_settings()
        
        if not settings.gemini_api_key:
            logger.error("GEMINI_API_KEY is not set")
            raise ConfigurationError(
                "GEMINI_API_KEY is not set. Please set it in your .env file."
            )
        
        logger.info("Configuring Gemini API...")
        genai.configure(api_key=settings.gemini_api_key)
        
        # Configure generation settings for large structured output
        generation_config = genai.GenerationConfig(
            temperature=0.7,
            max_output_tokens=65536,  # Maximum output for large JSON responses
        )
        
        self._model = genai.GenerativeModel(
            "gemini-2.5-flash",
            generation_config=generation_config
        )
        logger.info("Gemini API configured successfully with model: gemini-2.5-flash")
    
    @property
    def model(self) -> genai.GenerativeModel:
        """Get the configured Gemini model."""
        return self._model
    
    async def generate_content(self, prompt: str) -> str:
        """
        Generate content using Gemini API.
        
        Args:
            prompt: The prompt to send to Gemini.
            
        Returns:
            The generated text response.
            
        Raises:
            GeminiAPIError: If the API call fails.
        """
        logger.info("Generating content with Gemini API...")
        logger.debug(f"Prompt length: {len(prompt)} characters")
        logger.debug(f"Prompt preview: {prompt[:300]}...")
        
        try:
            response = self._model.generate_content(prompt)
            response_text = response.text
            logger.info(f"Gemini API response received, length: {len(response_text)} characters")
            logger.debug(f"Response preview: {response_text[:300]}...")
            return response_text
        except Exception as e:
            logger.error(f"Gemini API call failed: {str(e)}", exc_info=True)
            raise GeminiAPIError(
                message=str(e),
                details={"prompt_preview": prompt[:200] + "..." if len(prompt) > 200 else prompt}
            )


def get_gemini_client() -> GeminiClient:
    """Dependency injection for Gemini client."""
    return GeminiClient()
