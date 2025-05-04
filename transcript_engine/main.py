"""Main FastAPI application module for Transcript Memory Engine.

This module initializes the FastAPI application and sets up the core routes and dependencies.
"""

import logging.config
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any

# Import core dependencies and configuration
from transcript_engine.core.config import Settings, get_settings
from transcript_engine.core.dependencies import get_db
from transcript_engine.core.logging_config import LOGGING_CONFIG # Import logging config
# Import API routers
from transcript_engine.api.routers import transcripts
from transcript_engine.api.routers import chat

# Apply logging configuration
logging.config.dictConfig(LOGGING_CONFIG)

# Get a logger for the main module
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Transcript Memory Engine",
    description="A local-first application for processing and querying transcripts using RAG pipelines",
    version="0.1.0",
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, replace with specific origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include API routers
app.include_router(transcripts.router, prefix="/api/v1")
app.include_router(chat.router, prefix="/api/v1")

@app.on_event("startup")
async def startup_event():
    """Log application startup.
    """
    logger.info("Transcript Memory Engine application starting up...")
    # You could also initialize resources here if not using Depends/singletons

@app.on_event("shutdown")
async def shutdown_event():
    """Log application shutdown.
    """
    logger.info("Transcript Memory Engine application shutting down...")

@app.get("/health", response_model=Dict[str, Any])
async def health_check(settings: Settings = Depends(get_settings)) -> Dict[str, Any]:
    """Health check endpoint to verify the API is running.
    
    Returns:
        Dict[str, Any]: Health status information
    """
    return {
        "status": "healthy",
        "version": app.version,
        "environment": settings.environment,
    }

@app.get("/")
async def root() -> Dict[str, str]:
    """Root endpoint that returns basic API information.
    
    Returns:
        Dict[str, str]: Basic API information
    """
    return {
        "message": "Welcome to Transcript Memory Engine API",
        "version": app.version,
    } 