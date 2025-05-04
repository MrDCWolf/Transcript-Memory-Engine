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
PAGE_LIMIT = 10 # Max results per page for Limitless API (according to docs)
RATE_LIMIT_DELAY = 0.5 # Small delay between requests to be safe
MAX_RETRIES = 3 # Max retries for transient server errors (e.g., 504)
RETRY_DELAY_SECONDS = 5 # Delay between retries

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
    since_date: Optional[date] = None # Note: API uses date/start/end, not simple since_date
) -> List[TranscriptCreate]:
    """Fetches transcripts (lifelogs) from the Limitless API.

    Handles pagination using cursor.
    NOTE: Date filtering based on `since_date` is not yet implemented according to API docs.

    Args:
        settings: Application settings.
        since_date: Optional date to fetch transcripts created on or after (currently ignored).

    Returns:
        A list of TranscriptCreate objects.

    Raises:
        ValueError: If the Limitless API key is not configured.
        httpx.HTTPStatusError: If the API request fails.
    """
    api_key = settings.limitless_api_key
    if not api_key:
        logger.error("Limitless API key is missing in configuration.")
        raise ValueError("Limitless API key not configured.")

    logger.info(f"Starting fetch from Limitless API. Since: {since_date} (Note: date filtering not implemented)")

    headers = {
        "X-API-Key": api_key, # Correct header
        # "Accept": "application/json", # Not explicitly needed per docs
    }

    # Correct endpoint based on docs
    base_url = f"{LIMITLESS_API_BASE_URL}/lifelogs"
    
    # API uses date/start/end params, not a simple 'since'. 
    # For now, fetch all, implement date filtering later if needed.
    if since_date:
        logger.warning("'since_date' parameter is currently ignored. Fetching all lifelogs.")

    all_transcripts: list[TranscriptCreate] = []
    cursor: Optional[str] = None # Use cursor for pagination
    page = 1

    try:
        with httpx.Client(headers=headers, timeout=REQUEST_TIMEOUT) as client:
            while True:
                params: Dict[str, Any] = {"limit": PAGE_LIMIT}
                if cursor:
                    params["cursor"] = cursor
                
                current_retries = 0
                response = None # Initialize response to None
                
                # Inner loop for retries
                while current_retries < MAX_RETRIES:
                    try:
                        logger.debug(f"Fetching page {page} from {base_url} with params: {params} (Attempt {current_retries + 1}/{MAX_RETRIES})")
                        response = client.get(base_url, params=params)
                        response.raise_for_status() # Raise HTTPStatusError for bad responses (4xx, 5xx)
                        # If successful, break the retry loop
                        logger.debug(f"Successfully fetched page {page}.")
                        break 
                    except httpx.HTTPStatusError as exc:
                        # Check for retryable server errors (5xx)
                        if 500 <= exc.response.status_code < 600:
                            current_retries += 1
                            if current_retries < MAX_RETRIES:
                                logger.warning(
                                    f"Received status {exc.response.status_code} fetching page {page}. "
                                    f"Retrying in {RETRY_DELAY_SECONDS}s... ({current_retries}/{MAX_RETRIES})"
                                )
                                time.sleep(RETRY_DELAY_SECONDS)
                                continue # Retry the request
                            else:
                                logger.error(
                                    f"Received status {exc.response.status_code} fetching page {page}. "
                                    f"Max retries ({MAX_RETRIES}) exceeded."
                                )
                                raise # Re-raise the exception after max retries
                        else:
                            # Non-retryable HTTP error (e.g., 4xx client error)
                            logger.error(f"HTTP error fetching page {page}: {exc}", exc_info=True)
                            raise # Re-raise immediately
                    except httpx.RequestError as exc:
                         # Network-level error (connection, timeout, etc.)
                         logger.error(f"Network error fetching page {page}: {exc}", exc_info=True)
                         # Consider if these should be retried or are fatal
                         raise # Re-raise for now
                
                # If the retry loop finished because of an error (response is None or still has error status)
                # This check might be redundant if exceptions are always raised, but adds safety.
                if response is None or response.is_error:
                    logger.error(f"Failed to fetch page {page} after retries or due to non-retryable error.")
                    break # Exit the main pagination loop

                # --- Process successful response ---
                data = response.json()
                lifelogs_data = data.get("data", {}).get("lifelogs", [])
                next_cursor = data.get("meta", {}).get("lifelogs", {}).get("nextCursor")
                
                if not lifelogs_data:
                    logger.info("No lifelogs found on this page.")
                    break 

                logger.info(f"Fetched {len(lifelogs_data)} lifelogs on page {page}. Next cursor: {bool(next_cursor)}")
                
                for item in lifelogs_data:
                    lifelog_id = item.get("id")
                    title = item.get("title") # Can be None
                    transcript_content = item.get("markdown") # Use markdown field
                    
                    if not lifelog_id or not transcript_content:
                        logger.warning(f"Skipping item due to missing ID or markdown: {item}")
                        continue
                        
                    # Map to TranscriptCreate model
                    transcript_data = TranscriptCreate(
                        source="limitless",
                        source_id=lifelog_id,
                        title=title, 
                        content=transcript_content
                    )
                    all_transcripts.append(transcript_data)
                
                # --- Pagination Logic --- 
                if not next_cursor:
                    logger.info("No next cursor provided by API. Assuming end of data.")
                    break 
                
                cursor = next_cursor
                page += 1
                time.sleep(RATE_LIMIT_DELAY) # Be nice to the API between pages

    except httpx.HTTPStatusError as exc: 
        # This will catch errors re-raised from the retry loop (e.g., max retries exceeded or 4xx)
        logger.error(f"Limitless API request failed with status {exc.response.status_code}: {exc.response.text}")
        # Decide if we want to return partially fetched data or raise
        # For now, we let it implicitly return whatever was collected before the error
    except httpx.RequestError as exc:
        logger.error(f"Network error during Limitless API request: {exc}")
        # Let it implicitly return whatever was collected
    except Exception as exc:
        logger.error(f"Unexpected error processing Limitless response: {exc}", exc_info=True)
        # Let it implicitly return whatever was collected

    logger.info(f"Finished fetching from Limitless API. Total transcripts retrieved: {len(all_transcripts)}")
    return all_transcripts 