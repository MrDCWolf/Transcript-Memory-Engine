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
from transcript_engine.api.routers import ingestion # Add ingestion
from transcript_engine.api.routers import actionables as actionables_router # Import actionables router
from transcript_engine.api.routers import actionables_ui # Import actionables_ui router
from transcript_engine.api.routers import auth_google # Import auth_google router
# Remove incorrect imports
# from transcript_engine.api.routers import health, ingestion
from transcript_engine.database.crud import initialize_database # Correct import path
from transcript_engine.ingest.ingestion_service import INGESTION_STATUS # Import the status dict

# Configure logging
# TODO: Move logging config to a separate module/function
log_level = logging.INFO
logging.basicConfig(
    level=log_level,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

lifetime_data = {}

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    logger.info("Starting Transcript Memory Engine API...")

    # Reset service singletons (if any were created before startup)
    logger.info("Resetting service singletons...")
    # Example: If using a singleton pattern managed elsewhere
    # reset_services()

    # Reset INGESTION_STATUS on startup
    logger.info("Resetting ingestion status...")
    INGESTION_STATUS.update({
        "status": "idle",
        "last_run": INGESTION_STATUS.get("last_run", "Never"), # Keep last run time if available
        "last_error": None # Clear last error
    })

    # Load settings
    try:
        # Access settings to trigger loading/validation via pydantic-settings
        _ = get_settings() # Or use get_settings() if that's the dependency function
        logger.info("Settings loaded.")
    except Exception as e:
        logger.error(f"Failed to load settings on startup: {e}", exc_info=True)
        # Decide if you want to raise the error and stop startup
        raise

    # Initialize Database
    # Get settings first
    current_settings = get_settings()
    db_url = current_settings.database_url # Use the correct attribute name
    # Extract path from URL - assuming sqlite for now
    if not db_url.startswith("sqlite:///"):
        raise ValueError(f"Invalid database_url format: {db_url}. Expected 'sqlite:///path/to/db.sqlite'")
    db_path_str = db_url[len("sqlite:///"):]
    db_path = Path(db_path_str).resolve() # Convert to Path object

    logger.info(f"Ensuring database exists and is initialized at: {db_path}")
    try:
        conn = initialize_database(db_path)
        # Store connection if needed globally or close it
        # If using Depends(get_db), it might handle connections per-request
        if conn:
             conn.close() # Close the init connection
        logger.info("Database initialization check completed.")
    except Exception as e:
        logger.error(f"Failed to initialize database on startup: {e}", exc_info=True)
        raise

    # Initialize other services like LLM client, embedding model, vector store? 
    # Often better done lazily via Depends unless truly needed globally at startup
    # Example: initialize_llm_client()
    
    yield
    
    # Shutdown
    logger.info("Shutting down Transcript Memory Engine API...")
    # Clean up resources (e.g., close database connections, client sessions)
    # Example: if limitless_client was stored globally
    if "limitless_client" in lifetime_data:
        try:
            await lifetime_data["limitless_client"].close()
            logger.info("Limitless client session closed.")
        except Exception as e:
            logger.error(f"Error closing Limitless client: {e}", exc_info=True)
    # Close other resources...
    logger.info("Shutdown complete.")

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
app.include_router(ingestion.router) # Add the new ingestion router
app.include_router(actionables_router.router, prefix="/api/v1/actionables", tags=["Actionable Items"]) # Add actionables router
app.include_router(actionables_ui.router, tags=["Actionable Items UI"]) # Add actionables_ui router
app.include_router(auth_google.router, tags=["Google Authentication"]) # Add auth_google router

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