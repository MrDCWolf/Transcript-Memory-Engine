"""Main FastAPI application module for Transcript Memory Engine.

This module initializes the FastAPI application and sets up the core routes and dependencies.
"""

import logging
from contextlib import asynccontextmanager
from pathlib import Path
import uvicorn # Import uvicorn

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from typing import Dict, Any

# Import core dependencies and configuration
from transcript_engine.core.config import Settings, get_settings
from transcript_engine.core.dependencies import get_db
from transcript_engine.core.logging_config import LOGGING_CONFIG # Import logging config
# Import the singletons to reset them
from transcript_engine.core import dependencies as core_deps
# Import API routers
from transcript_engine.api.routers import transcripts
# Correct the chat router import
# from transcript_engine.api.routers import chat_ui
from transcript_engine.api.routers import chat as chat_ui_router
from transcript_engine.api.routers import settings as settings_router # Import settings router
# Remove incorrect imports
# from transcript_engine.api.routers import health, ingestion
from transcript_engine.database.crud import initialize_database # Correct import path

# Configure logging
# TODO: Move logging config to a separate module/function
log_level = logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting Transcript Memory Engine API...")
    
    # --- Reset Singletons --- 
    # Ensure services are recreated with potentially updated settings on startup
    logger.info("Resetting service singletons...")
    core_deps._embedding_service = None
    core_deps._vector_store = None
    core_deps._llm_service = None
    core_deps._retriever = None
    core_deps._rag_service = None
    # ----------------------
    
    # Initialize database on startup
    settings = get_settings() # Call get_settings to load (uses .env via config.py)
    # app.state.settings = settings # Remove storing in app state
    logger.info("Settings loaded.") # Simplified log
    
    db_url = settings.database_url # Use correct setting name
    # Extract path from URL
    if not db_url.startswith("sqlite:///"):
        raise ValueError(f"Invalid database_url format: {db_url}. Expected 'sqlite:///path/to/db.sqlite'")
    db_path_str = db_url[len("sqlite:///"):]
    db_path = Path(db_path_str).resolve()
    
    logger.info(f"Ensuring database exists and is initialized at: {db_path}")
    try:
        initialize_database(db_path) # Call with path
        logger.info("Database initialization check completed.")
    except Exception as e:
        logger.critical(f"FATAL: Database initialization failed: {e}", exc_info=True)
        # Prevent app startup if DB init fails
        raise RuntimeError(f"Database initialization failed: {e}") from e
    yield
    # --- Teardown --- 
    logger.info("Shutting down Transcript Memory Engine API...")
    db_conn = core_deps._db_conn # Access global directly for shutdown
    if db_conn:
        logger.info("Closing database connection...")
        db_conn.close()
        core_deps._db_conn = None # Clear the global
    else:
        logger.warning("No active database connection found to close during shutdown.")
    logger.info("Transcript Memory Engine API shutdown complete.")
    # ----------------

# Configure logging dictionary
uvicorn_log_config = LOGGING_CONFIG

# Create FastAPI app
app = FastAPI(
    title="Transcript Memory Engine API",
    description="API for processing transcripts and answering questions using RAG.",
    version="0.1.0",
    lifespan=lifespan
)

# Mount static files
static_dir = Path(__file__).resolve().parent.parent / "static"
app.mount("/static", StaticFiles(directory=str(static_dir)), name="static")

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
# Remove routers that don't exist
# app.include_router(health.router, prefix="/api/v1")
# app.include_router(ingestion.router, prefix="/api/v1")
# Include the Chat UI router using the correct variable name
app.include_router(chat_ui_router.router)
app.include_router(settings_router.router) # Include the settings router

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

if __name__ == "__main__":
    # Ensure settings load once before starting (uses .env via config.py)
    settings = get_settings()
    
    # Turn off reload for stability if needed during debugging
    # settings.api_reload = False 
    
    logger.info(f"Starting Uvicorn server on {settings.api_host}:{settings.api_port} with reload={settings.api_reload}")
    
    uvicorn.run(
        "transcript_engine.main:app", 
        host=settings.api_host,
        port=settings.api_port,
        reload=settings.api_reload, 
        # reload=False, # Revert forced reload off
        log_config=uvicorn_log_config, # Pass the logging config
        log_level=settings.api_log_level.lower() # Keep level setting
    ) 