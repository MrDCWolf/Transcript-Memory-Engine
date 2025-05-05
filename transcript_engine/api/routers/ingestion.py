"""API Router for triggering and monitoring transcript ingestion."""

import asyncio
import logging
import sqlite3
from typing import Optional, Dict, Any
from datetime import datetime, timezone, timedelta
# import json # No longer needed for SSE events
# import time # No longer needed for SSE generator

from fastapi import APIRouter, Depends, Request, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
# from sse_starlette.sse import EventSourceResponse # Remove SSE dependency

from transcript_engine.core.dependencies import (
    get_templates,
    get_db,
    get_limitless_client, 
    get_embedding_service,
    get_vector_store
)
# Import the status dict and defined stages
from transcript_engine.ingest.ingestion_service import run_ingestion_pipeline, INGESTION_STATUS, STAGES 
from transcript_engine.database import crud

logger = logging.getLogger(__name__)
router = APIRouter()

# --- Remove SSE Specific Code ---
# STREAM_DELAY = 0.5  
# MAX_STREAM_TIME = 3600 
# PROGRESS_STREAM_STORE: Dict[str, Any] = {"last_update": None, "generator": None}
# async def progress_event_generator(request: Request, templates: Jinja2Templates):
#    ... (Removed entire generator function) ...
# -------------------------------

# --- Update Background Task Runner ---
async def run_background_ingestion(
    db: Any, # Use actual type hint
    limitless_client: Any,
    embedding_service: Any,
    vector_store: Any,
    start_from: Optional[datetime]
):
    """Wrapper to run the pipeline in the background."""
    logger.info(f"Background task started for ingestion from: {start_from}")
    # The pipeline function now directly updates INGESTION_STATUS
    await run_ingestion_pipeline(
        db, limitless_client, embedding_service, vector_store, start_from
    )
    logger.info("Background ingestion task finished.")
    # No need to handle progress or errors here, pipeline function does it

# -------------------------------------

@router.get("/ingest/", response_class=HTMLResponse)
async def get_ingest_page(
    request: Request,
    db: sqlite3.Connection = Depends(get_db),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Serves the ingestion trigger page."""
    last_ingest_time_dt = crud.get_latest_limitless_start_time(db)
    last_ingest_time_str = last_ingest_time_dt.isoformat() if last_ingest_time_dt else "Never"
    
    # Pass the entire status dict for the template to use
    logger.info(f"Rendering ingest page. Current INGESTION_STATUS: {INGESTION_STATUS}")
    
    return templates.TemplateResponse(
        request=request, 
        name="ingest.html", 
        context={
            "last_ingest_time": last_ingest_time_str,
            "ingestion_status": INGESTION_STATUS, # Pass full status dict
            "all_stages": STAGES # Pass defined stages for the checklist
        }
    )

@router.post("/ingest/start", response_class=HTMLResponse)
async def start_ingestion(
    request: Request, # Needed for TemplateResponse
    background_tasks: BackgroundTasks,
    db: sqlite3.Connection = Depends(get_db),
    limitless_client = Depends(get_limitless_client),
    embedding_service = Depends(get_embedding_service),
    vector_store = Depends(get_vector_store),
    templates: Jinja2Templates = Depends(get_templates),
):
    """Triggers the ingestion pipeline in the background and returns initial progress UI."""
    # Check if already running using the status dict
    if INGESTION_STATUS.get("status") == "running":
        # Return an updated progress display indicating it's already running
        # Or raise HTTPException - let's return the current status display
        logger.warning("Ingestion start request received, but already running.")
        return templates.TemplateResponse(
            request=request,
            name="_ingest_progress.html",
            context={
                "ingestion_status": INGESTION_STATUS,
                "all_stages": STAGES,
                "polling": True # Indicate polling should continue
            }
        )
        # raise HTTPException(status_code=409, detail="Ingestion is already running.")

    # Determine start date (from last ingest + 1 second, or None)
    last_ingest_dt = crud.get_latest_limitless_start_time(db)
    start_from = last_ingest_dt + timedelta(seconds=1) if last_ingest_dt else None
    
    logger.info(f"Adding ingestion task to background queue. Start date: {start_from}")
    background_tasks.add_task(
        run_background_ingestion, 
        db, limitless_client, embedding_service, vector_store, start_from
    )
    logger.info("Ingestion task added.") 

    # Set status to running immediately (pipeline will update further)
    INGESTION_STATUS.update({
        "status": "running",
        "current_stage": "fetch", # Assume it starts with fetch
        "completed_stages": [],
        "message": "Ingestion task started in background...",
        "last_run": datetime.now(timezone.utc).isoformat(),
        "last_error": None
    })

    # Return the initial progress display with polling enabled
    return templates.TemplateResponse(
        request=request, 
        name="_ingest_progress.html", 
        context={
            "ingestion_status": INGESTION_STATUS,
            "all_stages": STAGES,
            "polling": True # Explicitly tell template to add polling attributes
        }
    )

# --- Add Polling Endpoint ---
@router.get("/ingest/status", response_class=HTMLResponse)
async def get_ingestion_status(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates)
):
    """Returns the current ingestion status as an HTML partial."""
    logger.debug(f"Polling request received. Current status: {INGESTION_STATUS.get('status')}")
    # Check if polling should continue
    is_still_running = INGESTION_STATUS.get("status") == "running"
    
    return templates.TemplateResponse(
        request=request,
        name="_ingest_progress.html",
        context={
            "ingestion_status": INGESTION_STATUS, # Pass the latest status
            "all_stages": STAGES,
            "polling": is_still_running # Tell template whether to continue polling
        }
    )
# ----------------------------

# --- Remove SSE Endpoint ---
# @router.get("/ingest/progress")
# async def ingestion_progress(request: Request, templates: Jinja2Templates = Depends(get_templates)):
#    ... (Removed endpoint) ...
# -------------------------- 