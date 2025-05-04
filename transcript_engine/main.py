"""Main FastAPI application module for Transcript Memory Engine.

This module initializes the FastAPI application and sets up the core routes and dependencies.
"""

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from typing import Dict, Any

# Import core dependencies and configuration
from transcript_engine.core.config import Settings, get_settings
from transcript_engine.core.dependencies import get_db
# Import API routers
from transcript_engine.api.routers import transcripts

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
app.include_router(transcripts.router)

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