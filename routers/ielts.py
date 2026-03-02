"""
IELTS API Router - Main router aggregating all IELTS endpoints.
"""

from fastapi import APIRouter

from routers.reading import router as reading_router
from routers.writing import router as writing_router
from routers.writing_evaluation import router as writing_evaluation_router
from routers.listening import router as listening_router

# Create main IELTS API router
router = APIRouter(prefix="/api/ielts", tags=["IELTS"])

# Include sub-routers
router.include_router(reading_router)
router.include_router(writing_router)
router.include_router(writing_evaluation_router)
router.include_router(listening_router)
