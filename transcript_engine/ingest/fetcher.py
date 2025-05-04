"""Module for fetching transcript data from the Limitless API.
"""

import logging
import httpx
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timezone
import time

from transcript_engine.database.models import TranscriptCreate
from transcript_engine.core.config import Settings

logger = logging.getLogger(__name__)

LIMITLESS_API_BASE_URL = "https://api.limitless.ai/v1"
REQUEST_TIMEOUT = 30.0 # seconds
PAGE_LIMIT = 100 # Max results per page for Limitless API
RATE_LIMIT_DELAY = 0.5 # Small delay between requests to be safe

def _parse_iso_datetime(timestamp_str: Optional[str]) -> Optional[datetime]:
    """Safely parses an ISO 8601 timestamp string, handling potential None values.
    
    Converts to timezone-aware UTC datetime.
    """
    if not timestamp_str:
        return None
    try:
        # datetime.fromisoformat handles common ISO 8601 formats including Z for UTC
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        # Ensure it's timezone-aware (make naive UTC if not)
        if dt.tzinfo is None:
             dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except (ValueError, TypeError) as e:
        logger.warning(f"Could not parse timestamp string '{timestamp_str}': {e}")
        return None

def fetch_transcripts(
    settings: Settings, 
    since_date: Optional[date] = None
) -> List[TranscriptCreate]:
    """Fetches transcript data from the Limitless /conversations endpoint.

    Handles pagination and incremental fetching based on since_date.

    Args:
        settings: The application settings containing the API key.
        since_date: Optional date to fetch transcripts created on or after this date.

    Returns:
        A list of TranscriptCreate objects.
        
    Raises:
        ValueError: If the API key is missing.
        httpx.RequestError: For network-related errors.
        httpx.HTTPStatusError: For API error responses (4xx, 5xx).
    """
    api_key = settings.limitless_api_key
    if not api_key:
        logger.error("Limitless API key is missing in configuration.")
        raise ValueError("Limitless API key not configured.")

    endpoint = f"{LIMITLESS_API_BASE_URL}/conversations"
    headers = {"Authorization": f"Bearer {api_key}"}
    all_fetched_transcripts: List[TranscriptCreate] = []
    starting_after: Optional[str] = None
    page_num = 1

    logger.info(f"Starting fetch from Limitless API. Since: {since_date}")

    try:
        with httpx.Client(headers=headers, timeout=REQUEST_TIMEOUT) as client:
            while True:
                params: Dict[str, Any] = {"limit": PAGE_LIMIT}
                if starting_after:
                    params["starting_after"] = starting_after
                
                logger.debug(f"Fetching page {page_num} from {endpoint} with params: {params}")
                response = client.get(endpoint, params=params)
                response.raise_for_status() # Raise HTTPStatusError for bad responses
                
                data = response.json()
                conversations = data.get("data", [])
                has_more = data.get("has_more", False)
                
                if not conversations:
                    logger.info("No conversations found on this page.")
                    break # Exit loop if no data

                logger.info(f"Fetched {len(conversations)} conversations on page {page_num}. Has more: {has_more}")
                
                oldest_date_on_page: Optional[date] = None
                last_item_id: Optional[str] = None
                
                for item in conversations:
                    conversation_id = item.get("conversation_id")
                    transcript_content = item.get("transcript")
                    created_at_str = item.get("created_at")
                    summary = item.get("summary")
                    
                    last_item_id = conversation_id # Track last ID for pagination

                    if not conversation_id or not transcript_content:
                        logger.warning(f"Skipping item due to missing ID or transcript: {item}")
                        continue
                        
                    created_datetime = _parse_iso_datetime(created_at_str)
                    item_date = created_datetime.date() if created_datetime else None
                    
                    # Update oldest date seen on this page (if valid)
                    if item_date:
                        if oldest_date_on_page is None or item_date < oldest_date_on_page:
                             oldest_date_on_page = item_date
                    
                    # Check if this item itself is older than since_date
                    # (Optional: could just rely on the oldest_date_on_page check below)
                    # if since_date and item_date and item_date < since_date:
                    #     logger.debug(f"Skipping item {conversation_id} older than since_date {since_date}")
                    #     continue 

                    # Map to TranscriptCreate model
                    transcript_data = TranscriptCreate(
                        source="limitless",
                        source_id=conversation_id,
                        title=summary, # Can be None
                        content=transcript_content
                    )
                    all_fetched_transcripts.append(transcript_data)
                
                # --- Pagination and Incremental Fetch Logic --- 
                if not has_more:
                    logger.info("No more pages to fetch (has_more is false).")
                    break # Exit loop
                
                # Check oldest date on page against since_date
                if since_date and oldest_date_on_page and oldest_date_on_page < since_date:
                    logger.info(f"Stopping pagination: Oldest item on page ({oldest_date_on_page}) is older than since_date ({since_date}).")
                    break # Exit loop
                    
                if not last_item_id:
                     logger.warning("Could not determine last item ID for pagination. Stopping.")
                     break # Should not happen if conversations list was not empty
                     
                # Prepare for next page
                starting_after = last_item_id
                page_num += 1
                time.sleep(RATE_LIMIT_DELAY) # Be nice to the API

    except httpx.HTTPStatusError as exc:
        logger.error(f"Limitless API request failed with status {exc.response.status_code}: {exc.response.text}")
        raise
    except httpx.RequestError as exc:
        logger.error(f"Network error during Limitless API request: {exc}")
        raise
    except Exception as exc:
        logger.error(f"Unexpected error processing Limitless response: {exc}", exc_info=True)
        raise # Re-raise other unexpected errors

    logger.info(f"Finished fetching from Limitless API. Total transcripts retrieved: {len(all_fetched_transcripts)}")
    return all_fetched_transcripts 