"""API Router for Actionable Items feature."""

import sqlite3
import logging
from datetime import date
from typing import List, Optional, Dict, Any

from fastapi import APIRouter, Depends, HTTPException, status, Form
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, validator, Field
from enum import Enum

from transcript_engine.features.actionables_utils import get_transcript_for_timeframe
from transcript_engine.features.actionables_service import scan_transcript_for_actionables
from transcript_engine.features.actionables_models import CandidateActionableItem, GoogleCalendarEventSchema, GoogleTaskSchema
from transcript_engine.interfaces.llm_interface import LLMInterface
from transcript_engine.core.dependencies import get_db, get_llm_service
from transcript_engine.api.routers.auth_google import get_google_credentials
from google.oauth2.credentials import Credentials
from transcript_engine.features import google_services
import json

logger = logging.getLogger(__name__)
router = APIRouter()

class TimeframeEnum(str, Enum):
    morning = "morning"
    afternoon = "afternoon"
    evening = "evening"

class ScanRequest(BaseModel):
    date: date
    timeframe: TimeframeEnum

    @validator('date')
    def date_must_not_be_in_future(cls, v):
        if v > date.today():
            raise ValueError("Date cannot be in the future")
        return v

class CandidateItemResponse(BaseModel):
    snippet: str
    suggested_category: str
    raw_entities: Optional[str] = None

class ScanResponse(BaseModel):
    candidates: List[CandidateItemResponse]

# --- Models for Prepare Export Endpoint ---
class ConfirmedItemRequest(BaseModel):
    snippet: str
    final_category: str # User-confirmed category: "EVENT", "TASK", "REMINDER"
    original_snippet: str # For reference or if user edits were reverted
    original_category: str
    original_entities: Optional[str] = None
    # user_edits could be a dict of fields the user explicitly set in the UI,
    # overriding snippet or providing structured details directly.
    # For simplicity in this phase, we'll primarily use the edited snippet and final_category.
    # If user_edits contains structured data, the service layer might use it directly.
    user_edits: Optional[Dict[str, Any]] = None 

class PrepareExportRequest(BaseModel):
    # This will be a list of form data items, so we need to parse it carefully.
    # The form sends data like: confirmed_indices=0, snippet_0="text", category_0="EVENT", ...
    # We'll handle the parsing from Form data directly in the endpoint for now.
    # For a JSON request body, it would be: confirmed_items: List[ConfirmedItemRequest]
    pass # Actual parsing from Form data will be done in the endpoint itself.

class ExportableItem(BaseModel):
    type: str  # "EVENT", "TASK", "REMINDER"
    details: Dict[str, Any]  # This will be the structured data, e.g., GoogleCalendarEventSchema as dict
    original_snippet: str # Pass through for UI reference
    final_category: str # Pass through for UI reference

class PrepareExportResponse(BaseModel):
    exportable_items: List[ExportableItem]
    errors: List[Dict[str, str]] = [] # To report any items that failed extraction

# --- Models for Extract Structured Data Endpoint (Backend) ---
class ConfirmedItemPayload(BaseModel):
    # Data sent from UI router to this backend endpoint for a single item
    # Includes data originally from CandidateActionableItem plus user edits
    user_snippet: str # The snippet text as confirmed/edited by the user
    final_category: str # User-confirmed category: "EVENT", "TASK", "REMINDER"
    target_date: date # The original date of the transcript for context
    # Optional: pass through original data if useful for logging or complex merging
    original_snippet: Optional[str] = None
    original_category: Optional[str] = None
    original_entities: Optional[str] = None 

class ExtractStructuredRequest(BaseModel):
    confirmed_items: List[ConfirmedItemPayload]

class ExtractedItemDetail(BaseModel):
    type: str  # "EVENT", "TASK", "REMINDER"
    details: Optional[Dict[str, Any]] = None # Validated structured data or None if extraction failed for this item
    user_snippet: str # Pass through for UI reference
    # We add an error field per item if extraction fails for this specific item
    error_message: Optional[str] = None

class ExtractStructuredResponse(BaseModel):
    processed_items: List[ExtractedItemDetail]

# --- Models for Export to Google Endpoint (Backend) ---
class ExportItemToGoogleRequest(BaseModel):
    service_type: str # "event" / "calendar" or "task"
    item_details: Dict[str, Any] # The structured data for the item, matches schema like GoogleCalendarEventSchema

class ExportItemToGoogleResponse(BaseModel):
    success: bool
    message: str
    item_link: Optional[str] = None # Link to the created Google Calendar event, or ID for Task

@router.post("/scan", response_model=ScanResponse)
async def scan_actionables_endpoint(
    request: ScanRequest,
    db: sqlite3.Connection = Depends(get_db),
    llm_service: LLMInterface = Depends(get_llm_service),
):
    """
    Scans transcripts for a given date and timeframe to identify potential actionable items.
    """
    logger.info(f"Received request to scan actionables for date: {request.date}, timeframe: {request.timeframe.value}")

    try:
        # Phase FE-1.1: Timeframe-based Transcript Retrieval
        transcript_segment = get_transcript_for_timeframe(
            db=db, target_date=request.date, timeframe_key=request.timeframe.value
        )

        if transcript_segment is None: # Indicates an error like invalid timeframe key from utils
            logger.error(f"Error retrieving transcript segment for {request.date}, {request.timeframe.value}. get_transcript_for_timeframe returned None.")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Error retrieving transcript data for the specified timeframe."
            )
        
        if not transcript_segment.strip():
            logger.info(f"No transcript content found for date {request.date}, timeframe {request.timeframe.value}. Returning empty list.")
            return ScanResponse(candidates=[])

        # Phase FE-1.2: Local LLM Candidate Identification Logic
        candidate_items: List[CandidateActionableItem] = scan_transcript_for_actionables(
            transcript_segment=transcript_segment,
            llm_service=llm_service,
            target_date=request.date,
            timeframe_key=request.timeframe.value,
        )
        
        # Convert CandidateActionableItem (from service) to CandidateItemResponse (for API)
        response_candidates = [
            CandidateItemResponse(
                snippet=item.snippet,
                suggested_category=item.suggested_category,
                raw_entities=item.raw_entities
            )
            for item in candidate_items
        ]

        logger.info(f"Found {len(response_candidates)} actionable candidates for {request.date}, {request.timeframe.value}.")
        return ScanResponse(candidates=response_candidates)

    except HTTPException: # Re-raise HTTPExceptions directly
        raise
    except sqlite3.Error as db_err:
        logger.error(f"Database error during actionable scan for {request.date}, {request.timeframe.value}: {db_err}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="A database error occurred while processing your request."
        )
    except Exception as e:
        logger.error(f"Unexpected error during actionable scan for {request.date}, {request.timeframe.value}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your request."
        ) 

@router.post("/extract_structured", response_model=ExtractStructuredResponse)
async def extract_structured_actionables_endpoint(
    request_payload: ExtractStructuredRequest,
    # llm_service: LLMInterface = Depends(get_llm_service) # OpenAI client is created inside the service function
    # db: sqlite3.Connection = Depends(get_db) # Not directly needed here, service has what it needs
):
    """Backend endpoint to take confirmed items and extract structured data using a cloud LLM."""
    logger.info(f"Received request to extract structured data for {len(request_payload.confirmed_items)} items.")
    
    processed_items_response: List[ExtractedItemDetail] = []

    for item_payload in request_payload.confirmed_items:
        logger.debug(f"Processing item for structured extraction: Category '{item_payload.final_category}', Snippet '{item_payload.user_snippet[:50]}...'")
        try:
            # Ensure target_date is passed to the service function
            structured_details = await run_in_threadpool(
                extract_structured_data_for_item, 
                item_snippet=item_payload.user_snippet, 
                item_category=item_payload.final_category,
                target_date=item_payload.target_date
            )
            
            if structured_details:
                processed_items_response.append(ExtractedItemDetail(
                    type=item_payload.final_category,
                    details=structured_details,
                    user_snippet=item_payload.user_snippet
                ))
                logger.info(f"Successfully extracted structured data for item: {item_payload.user_snippet[:30]}...")
            else:
                logger.warning(f"Failed to extract structured data for item (snippet: '{item_payload.user_snippet[:50]}...', category: {item_payload.final_category}). Service returned None.")
                processed_items_response.append(ExtractedItemDetail(
                    type=item_payload.final_category,
                    user_snippet=item_payload.user_snippet,
                    details=None, # Explicitly None
                    error_message=f"Could not extract structured details. OpenAI API key might be missing or extraction failed."
                ))

        except Exception as e:
            logger.error(f"Unexpected error during structured extraction for item '{item_payload.user_snippet[:50]}...': {e}", exc_info=True)
            processed_items_response.append(ExtractedItemDetail(
                type=item_payload.final_category,
                user_snippet=item_payload.user_snippet,
                details=None,
                error_message=f"An unexpected server error occurred during extraction: {str(e)[:100]}"
            ))
            
    logger.info(f"Finished structured data extraction. Processed {len(request_payload.confirmed_items)} items resulting in {len(processed_items_response)} output items.")
    return ExtractStructuredResponse(processed_items=processed_items_response) 

@router.post("/export_to_google", response_model=ExportItemToGoogleResponse)
async def export_item_to_google_endpoint(
    request_payload: ExportItemToGoogleRequest,
    creds: Optional[Credentials] = Depends(get_google_credentials),
    settings: Settings = Depends(get_settings) 
):
    """Backend endpoint to export a single structured item to Google Calendar or Tasks."""
    logger.info(f"Received request to export item to Google. Service: {request_payload.service_type}")

    if not creds:
        logger.warning("Google OAuth credentials not found. User needs to authenticate.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google authentication required. Please login with Google first."
        )

    export_func = None
    parsed_details_model = None
    service_name_for_log = request_payload.service_type.lower()

    if service_name_for_log == "event" or service_name_for_log == "calendar":
        service_name_for_log = "Calendar" # For user messages
        export_func = google_services.add_to_google_calendar
        try:
            parsed_details_model = GoogleCalendarEventSchema(**request_payload.item_details)
        except Exception as e:
            logger.error(f"Pydantic validation error for GoogleCalendarEventSchema: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid event details: {e}")
    elif service_name_for_log == "task":
        service_name_for_log = "Tasks" # For user messages
        export_func = google_services.add_to_google_tasks
        try:
            parsed_details_model = GoogleTaskSchema(**request_payload.item_details)
        except Exception as e:
            logger.error(f"Pydantic validation error for GoogleTaskSchema: {e}", exc_info=True)
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Invalid task details: {e}")
    else:
        logger.error(f"Unsupported service_type for export: {request_payload.service_type}")
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Unsupported service_type for export: '{request_payload.service_type}'. Expected 'calendar' or 'task'.")

    try:
        result_link_or_id = await run_in_threadpool(export_func, creds, parsed_details_model)
        
        if result_link_or_id:
            logger.info(f"Successfully exported item to Google {service_name_for_log}. Result: {result_link_or_id}")
            return ExportItemToGoogleResponse(
                success=True, 
                message=f"Successfully exported to Google {service_name_for_log}!",
                item_link=result_link_or_id
            )
        else:
            logger.error(f"Failed to export item to Google {service_name_for_log}. Service function returned None.")
            return ExportItemToGoogleResponse(
                success=False, 
                message=f"Failed to export to Google {service_name_for_log}. Check server logs for details."
            )
    except HttpError as he:
        logger.error(f"Google API HttpError during export to {service_name_for_log}: {he}", exc_info=True)
        error_content = he.content.decode('utf-8') if isinstance(he.content, bytes) else str(he.content)
        detail_msg = "Google API error"
        try: 
            error_json = json.loads(error_content)
            detail_msg = error_json.get("error", {}).get("message", detail_msg)
        except: 
            detail_msg = error_content[:200] or detail_msg # Use raw content if not json or no message field
        return ExportItemToGoogleResponse(
                success=False, 
                message=f"Google API Error for {service_name_for_log}: {detail_msg}"
            )
    except Exception as e:
        logger.error(f"Unexpected error during export to Google {service_name_for_log}: {e}", exc_info=True)
        return ExportItemToGoogleResponse(
            success=False, 
            message=f"An unexpected server error occurred while exporting to {service_name_for_log}: {str(e)[:100]}"
        ) 