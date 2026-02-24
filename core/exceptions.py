"""
Custom exceptions for the IELTS API.
"""

from typing import Any, Optional


class IELTSAPIException(Exception):
    """Base exception for IELTS API errors."""
    
    def __init__(
        self,
        message: str,
        status_code: int = 500,
        details: Optional[Any] = None
    ):
        self.message = message
        self.status_code = status_code
        self.details = details
        super().__init__(self.message)


class GeminiAPIError(IELTSAPIException):
    """Exception raised when Gemini API call fails."""
    
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            message=f"Gemini API Error: {message}",
            status_code=502,
            details=details
        )


class JSONParseError(IELTSAPIException):
    """Exception raised when JSON parsing fails."""
    
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            message=f"JSON Parse Error: {message}",
            status_code=500,
            details=details
        )


class SchemaValidationError(IELTSAPIException):
    """Exception raised when schema validation fails."""
    
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            message=f"Schema Validation Error: {message}",
            status_code=500,
            details=details
        )


class ConfigurationError(IELTSAPIException):
    """Exception raised for configuration issues."""
    
    def __init__(self, message: str, details: Optional[Any] = None):
        super().__init__(
            message=f"Configuration Error: {message}",
            status_code=500,
            details=details
        )
