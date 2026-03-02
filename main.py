"""
AnyExamAI - Exam Generation API (FastAPI Backend)

Endpoints:
- GET /api/ielts/reading
- GET /api/ielts/writing
- GET /api/ielts/listening
"""

import logging
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, RedirectResponse

import gradio as gr

from core.config import get_settings
from core.exceptions import IELTSAPIException
from routers.ielts import router as ielts_router
from routers.speaking import create_speaking_app


# --------------------------------------------------
# Logging
# --------------------------------------------------
logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s | %(levelname)-8s | %(name)-30s | %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)

# Set third-party loggers to WARNING to reduce noise
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)
logging.getLogger("uvicorn").setLevel(logging.INFO)
logging.getLogger("uvicorn.access").setLevel(logging.INFO)

logger = logging.getLogger(__name__)


# --------------------------------------------------
# App Lifespan
# --------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    logger.info("Starting AnyExamAI API")
    logger.info(f"CORS Origins: {settings.cors_origins}")
    yield
    logger.info("Shutting down AnyExamAI API")


# --------------------------------------------------
# App Initialization
# --------------------------------------------------
settings = get_settings()

app = FastAPI(
    title="AnyExamAI",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# --------------------------------------------------
# Request Logging Middleware
# --------------------------------------------------
@app.middleware("http")
async def log_requests(request: Request, call_next):
    """Log all incoming requests and their responses."""
    start_time = time.time()
    
    # Log request
    logger.info(f">>> Request: {request.method} {request.url.path}")
    if request.query_params:
        logger.debug(f"    Query params: {dict(request.query_params)}")
    
    # Process request
    response = await call_next(request)
    
    # Log response
    process_time = time.time() - start_time
    logger.info(f"<<< Response: {response.status_code} | Time: {process_time:.2f}s")
    
    return response


# --------------------------------------------------
# Global Exception Handler
# --------------------------------------------------
@app.exception_handler(IELTSAPIException)
async def ielts_exception_handler(request: Request, exc: IELTSAPIException):
    logger.error(f"IELTS API Error: {exc.message}", exc_info=True)
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": exc.__class__.__name__,
            "message": exc.message,
            "details": exc.details,
        },
    )


# --------------------------------------------------
# Routes
# --------------------------------------------------
@app.get("/health", tags=["Health"])
async def health_check():
    return {"status": "healthy"}


@app.get("/", tags=["Root"])
async def root():
    return {
        "name": app.title,
        "version": app.version,
        "docs": "/docs",
    }


# IELTS Router
app.include_router(ielts_router)


@app.get(
    "/api/ielts/speaking",
    tags=["IELTS"],
    summary="IELTS Speaking Mock Test",
    description="Opens the interactive IELTS Speaking Mock Test UI powered by an AI examiner. "
                "Redirects to the Gradio-based speaking test interface at `/speaking`.",
)
async def speaking_test():
    """Redirect to the IELTS Speaking Test Gradio UI."""
    return RedirectResponse(url="/speaking")


# Speaking Test (Gradio UI) — mounted at /speaking
speaking_app = create_speaking_app()
app = gr.mount_gradio_app(app, speaking_app, path="/speaking")


# --------------------------------------------------
# Local Run
# --------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
    )