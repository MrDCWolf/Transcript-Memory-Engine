"""API Router for Actionable Items UI (HTMX)."""

import logging
from datetime import date
from typing import List, Dict, Any
import json

import httpx
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from transcript_engine.api.routers.actionables import TimeframeEnum # For form validation
from transcript_engine.core.dependencies import get_templates, get_settings
from transcript_engine.core.config import Settings

logger = logging.getLogger(__name__)
router = APIRouter()

@router.get("/actionables", response_class=HTMLResponse, name="actionables_dashboard")
async def get_actionables_dashboard_page(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
):
    """Serves the main Actionable Items dashboard page."""
    logger.info("Serving Actionable Items dashboard page.")
    return templates.TemplateResponse(
        "actionables/actionables_dashboard.html",
        {"request": request}
    )

@router.post("/actionables/scan_results", response_class=HTMLResponse, name="scan_actionable_results")
async def post_scan_actionable_results(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates),
    settings: Settings = Depends(get_settings),
    scan_date: date = Form(..., alias="date"), # Alias for form field name
    timeframe: TimeframeEnum = Form(...)
):
    """Handles the HTMX form submission to scan for actionables and returns an HTML partial."""
    logger.info(f"Received HTMX request to scan actionables for date: {scan_date}, timeframe: {timeframe.value}")

    api_scan_url = f"http://{settings.api_host}:{settings.api_port}/api/v1/actionables/scan"
    payload = {"date": scan_date.isoformat(), "timeframe": timeframe.value}

    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(api_scan_url, json=payload)
            response.raise_for_status() # Raise an exception for 4XX/5XX responses
            scan_data = response.json() # Expects ScanResponse format
            candidates = scan_data.get("candidates", [])
            
            logger.debug(f"Received {len(candidates)} candidates from backend API for {scan_date}, {timeframe.value}")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling backend /actionables/scan API: {e.response.status_code} - {e.response.text}", exc_info=True)
        # Render the partial with an error message
        error_message = f"Error communicating with the backend API: {e.response.status_code}. Details: {e.response.text[:200]}..."
        if e.response.status_code == 422:
            try:
                detail = e.response.json().get("detail")
                if isinstance(detail, list) and detail:
                    error_message = f"Invalid input: {detail[0].get('msg', 'Please check your input.')}"
                elif isinstance(detail, str):
                    error_message = f"Invalid input: {detail}"
                else:
                    error_message = "Invalid input. Please check the date and timeframe."
            except Exception: # pylint: disable=broad-except
                 pass # Stick with the generic status code message

        return templates.TemplateResponse(
            "actionables/_actionables_results_list.html",
            {"request": request, "candidates": [], "error": error_message},
            status_code=e.response.status_code if e.response.status_code >= 400 else 500
        )
    except httpx.RequestError as e:
        logger.error(f"Request error calling backend /actionables/scan API: {e}", exc_info=True)
        return templates.TemplateResponse(
            "actionables/_actionables_results_list.html",
            {"request": request, "candidates": [], "error": "Could not connect to the backend service."},
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE
        )
    except Exception as e: # Catch-all for other unexpected errors
        logger.error(f"Unexpected error processing scan results for {scan_date}, {timeframe.value}: {e}", exc_info=True)
        return templates.TemplateResponse(
            "actionables/_actionables_results_list.html",
            {"request": request, "candidates": [], "error": "An unexpected error occurred while processing your request."},
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR
        )
    
    return templates.TemplateResponse(
        "actionables/_actionables_results_list.html",
        {"request": request, "candidates": candidates, "original_scan_date": scan_date.isoformat()}
    )

@router.post("/actionables/prepare_export_ui", response_class=HTMLResponse, name="prepare_actionables_for_export")
async def post_prepare_actionables_for_export(
    request: Request, # Used to access raw form data
    templates: Jinja2Templates = Depends(get_templates),
    settings: Settings = Depends(get_settings),
    # We don't define Form fields here one by one because they are dynamic (snippet_0, category_0, snippet_1 etc.)
):
    """Handles HTMX form submission of confirmed/edited actionable items,
    calls backend to get structured data, and returns an HTML partial 
    listing items ready for Google export.
    """
    form_data = await request.form()
    logger.debug(f"Received form data for prepare_export_ui: {form_data}")

    confirmed_payloads: List[Dict[str, Any]] = [] # Will be List[ConfirmedItemPayload]
    # The `confirmed_indices` field contains the indices of the items that were checked.
    confirmed_indices = form_data.getlist("confirmed_indices")
    
    original_scan_date_str = form_data.get("original_scan_date") # Need to pass this from form
    if not original_scan_date_str:
        logger.error("Original scan date not found in form submission for prepare_export_ui.")
        return templates.TemplateResponse(
            "actionables/_exportable_items_list.html",
            {"request": request, "general_error": "Critical error: Original scan date was not submitted. Cannot process items."},
            status_code=status.HTTP_400_BAD_REQUEST
        )
    try:
        target_date_for_context = date.fromisoformat(original_scan_date_str)
    except ValueError:
        logger.error(f"Invalid original scan date format: {original_scan_date_str}")
        return templates.TemplateResponse(
            "actionables/_exportable_items_list.html",
            {"request": request, "general_error": "Critical error: Invalid original scan date format submitted."},
            status_code=status.HTTP_400_BAD_REQUEST
        )

    for index_str in confirmed_indices:
        try:
            idx = int(index_str) # index from the checkbox value
            # Check if the item was discarded (checkbox disabled by JS)
            # If checkbox is disabled, it might not be submitted. Relying on confirmed_indices solely.
            
            user_snippet = form_data.get(f"snippet_{idx}")
            final_category = form_data.get(f"category_{idx}")
            # raw_entities_edited = form_data.get(f"entities_{idx}") # User can edit entities too

            original_snippet = form_data.get(f"original_snippet_{idx}")
            original_category = form_data.get(f"original_category_{idx}")
            original_entities = form_data.get(f"original_entities_{idx}")

            if user_snippet and final_category:
                payload_item = {
                    "user_snippet": user_snippet,
                    "final_category": final_category,
                    "target_date": target_date_for_context.isoformat(), # Pass the original scan date for context
                    "original_snippet": original_snippet,
                    "original_category": original_category,
                    "original_entities": original_entities,
                    # "user_edits": {"raw_entities": raw_entities_edited} # Example if passing more edits
                }
                confirmed_payloads.append(payload_item)
            else:
                logger.warning(f"Skipping item at index {idx} due to missing snippet or category in form data.")
        except ValueError:
            logger.warning(f"Invalid index found in confirmed_indices: {index_str}")
            continue # Skip this index

    if not confirmed_payloads:
        logger.info("No items were confirmed or successfully parsed from the form for export preparation.")
        return templates.TemplateResponse(
            "actionables/_exportable_items_list.html",
            {"request": request, "processed_items": []} # No items to process
        )

    # Call the backend API to extract structured data
    backend_api_url = f"http://{settings.api_host}:{settings.api_port}/api/v1/actionables/extract_structured"
    backend_payload = {"confirmed_items": confirmed_payloads}

    processed_items_for_template = []
    general_error_for_template = None

    try:
        async with httpx.AsyncClient(timeout=60.0) as client: # Increased timeout for potentially long LLM calls
            response = await client.post(backend_api_url, json=backend_payload)
            response.raise_for_status()
            backend_response_data = response.json()
            processed_items_for_template = backend_response_data.get("processed_items", [])
            logger.info(f"Received {len(processed_items_for_template)} processed items from backend for structured extraction.")

    except httpx.HTTPStatusError as e:
        logger.error(f"HTTP error calling backend /extract_structured API: {e.response.status_code} - {e.response.text}", exc_info=True)
        general_error_for_template = f"Error calling backend for structured extraction: {e.response.status_code}. Check logs."
        if e.response.status_code == 422:
            try: general_error_for_template = f"Invalid data sent to backend: {e.response.json().get('detail', e.response.text)}" 
            except: pass
    except httpx.RequestError as e:
        logger.error(f"Request error calling backend /extract_structured API: {e}", exc_info=True)
        general_error_for_template = "Could not connect to the backend service for structured extraction."
    except Exception as e:
        logger.error(f"Unexpected error during prepare_export_ui: {e}", exc_info=True)
        general_error_for_template = "An unexpected server error occurred while preparing items for export."

    return templates.TemplateResponse(
        "actionables/_exportable_items_list.html",
        {
            "request": request, 
            "processed_items": processed_items_for_template, 
            "general_error": general_error_for_template,
            "original_scan_date": original_scan_date_str # Pass for next step if needed
        }
    )

@router.post("/actionables/export_item_to_google_ui", response_class=HTMLResponse, name="export_item_to_google")
async def post_export_item_to_google_ui(
    request: Request, # For logging or other context if needed
    settings: Settings = Depends(get_settings),
    service_type: str = Form(...),
    item_json: str = Form(...) # item_details from hx-vals will come as a JSON string
):
    """Handles HTMX request to export a single item to Google. Calls the backend API.
    Returns an HTML snippet indicating success or failure for that item.
    """
    logger.info(f"Received UI request to export item to Google. Service: {service_type}")

    try:
        item_details_dict = json.loads(item_json)
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding item_json for export: {e}. Data: {item_json}", exc_info=True)
        return PlainTextResponse(f"<span class=\"text-danger\">Error: Invalid item data format.</span>", status_code=400)

    backend_export_url = f"http://{settings.api_host}:{settings.api_port}/api/v1/actionables/export_to_google"
    payload = {
        "service_type": service_type,
        "item_details": item_details_dict
    }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(backend_export_url, json=payload)
            
            # No raise_for_status() here, as we want to handle specific responses for UI feedback
            response_data = response.json()

            if response.status_code == status.HTTP_200_OK and response_data.get("success"):                
                item_link = response_data.get("item_link")
                link_html = f" <a href='{item_link}' target='_blank'>(View)</a>" if item_link and item_link.startswith("http") else f" (ID: {item_link})" if item_link else ""
                logger.info(f"Successfully exported item via backend. Message: {response_data.get('message')}{link_html}")
                return PlainTextResponse(f"<span class=\"text-success\">{response_data.get('message', 'Success!')}{link_html}</span>")
            elif response.status_code == status.HTTP_401_UNAUTHORIZED:
                logger.warning("Export failed due to 401 Unauthorized from backend. User needs to login to Google.")
                login_url = request.url_for("google_login")
                return PlainTextResponse(f"<span class=\"text-danger\">Auth Required: <a href='{login_url}' target='_blank'>Login with Google</a></span>")
            else:
                error_message = response_data.get("message", response_data.get("detail", "Failed to export. Please try again."))
                logger.error(f"Export failed. Backend status: {response.status_code}, message: {error_message}")
                return PlainTextResponse(f"<span class=\"text-danger\">Error: {error_message}</span>")

    except httpx.RequestError as e:
        logger.error(f"Request error calling backend /export_to_google API: {e}", exc_info=True)
        return PlainTextResponse(f"<span class=\"text-danger\">Error: Could not connect to backend service.</span>", status_code=503)
    except Exception as e: # Catch-all for other unexpected errors
        logger.error(f"Unexpected error during export_item_to_google_ui: {e}", exc_info=True)
        return PlainTextResponse(f"<span class=\"text-danger\">Error: An unexpected error occurred.</span>", status_code=500)
 