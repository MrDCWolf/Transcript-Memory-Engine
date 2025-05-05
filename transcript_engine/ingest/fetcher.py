"""Module for fetching transcript data from the Limitless API.
"""

import logging
import httpx
import asyncio # Import asyncio for sleep
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timezone

from transcript_engine.database.models import TranscriptCreate
from transcript_engine.core.config import Settings

logger = logging.getLogger(__name__)

LIMITLESS_API_BASE_URL = "https://api.limitless.ai/v1"
REQUEST_TIMEOUT = 60.0 # Increased timeout slightly
PAGE_LIMIT = 10 # Max results per page for Limitless API (according to docs)
RATE_LIMIT_DELAY = 0.5 # Small delay between requests to be safe
# Enhanced Retry Logic
MAX_RETRIES = 10 # Increased retries
INITIAL_RETRY_DELAY_SECONDS = 5 # Initial delay
MAX_RETRY_DELAY_SECONDS = 60 # Cap delay at 1 minute

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

async def fetch_transcripts(
    api_key: str,
    # Accept start/end times (ISO format strings) instead of target_date
    start_time_iso: Optional[str] = None, 
    end_time_iso: Optional[str] = None, 
    timezone: str = "UTC",
) -> list[TranscriptCreate]:
    """Fetch transcripts (lifelogs) from the Limitless API within a time range.

    Handles pagination and retries on 5xx errors with exponential backoff.

    Args:
        api_key: The Limitless API key.
        start_time_iso: Optional start datetime in ISO format (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
        end_time_iso: Optional end datetime in ISO format.
        timezone: IANA timezone specifier. Defaults to UTC.

    Returns:
        List of TranscriptCreate objects fetched for the period.
    """
    base_url = f"{LIMITLESS_API_BASE_URL}/lifelogs"
    headers = {"X-API-Key": api_key}
    transcripts = []
    cursor = None
    page = 1
    # Log the time range being fetched
    fetch_range_log = f"from {start_time_iso}" if start_time_iso else "latest"
    if end_time_iso:
         fetch_range_log += f" to {end_time_iso}"
    
    async with httpx.AsyncClient(timeout=REQUEST_TIMEOUT) as client:
        while True:
            params = {
                "timezone": timezone,
                "includeMarkdown": "true",
                "includeHeadings": "true",
                "limit": str(PAGE_LIMIT),
                "direction": "asc",  # Fetch oldest first within the range for sequential processing
            }
            # Use start/end parameters based on provided ISO strings
            if start_time_iso:
                params["start"] = start_time_iso
            if end_time_iso:
                params["end"] = end_time_iso
            # Remove date parameter
            # if target_date:
            #     params["date"] = target_date
            if cursor:
                params["cursor"] = cursor

            current_retries = 0
            response = None
            
            while current_retries < MAX_RETRIES:
                try:
                    logger.debug(f"Fetching page {page} for range {fetch_range_log} (Attempt {current_retries + 1}/{MAX_RETRIES})")
                    response = await client.get(base_url, headers=headers, params=params)
                    response.raise_for_status()
                    logger.debug(f"Successfully fetched page {page}.")
                    break
                except httpx.HTTPStatusError as exc:
                    if 500 <= exc.response.status_code < 600:
                        current_retries += 1
                        if current_retries < MAX_RETRIES:
                            delay = min(INITIAL_RETRY_DELAY_SECONDS * (2 ** (current_retries - 1)), MAX_RETRY_DELAY_SECONDS)
                            logger.warning(
                                f"Received status {exc.response.status_code} fetching page {page} for range {fetch_range_log}. "
                                f"Retrying in {delay:.1f}s... ({current_retries}/{MAX_RETRIES})"
                            )
                            await asyncio.sleep(delay)
                            continue
                        else:
                            logger.error(
                                f"Received status {exc.response.status_code} fetching page {page} for range {fetch_range_log}. "
                                f"Max retries ({MAX_RETRIES}) exceeded."
                            )
                            return transcripts # Return data fetched so far
                    else:
                        logger.error(f"Non-retryable HTTP error fetching page {page} for range {fetch_range_log}: {exc}", exc_info=True)
                        return transcripts
                except httpx.RequestError as exc:
                     logger.error(f"Network error fetching page {page} for range {fetch_range_log}: {exc}", exc_info=True)
                     return transcripts
            
            if response is None or response.is_error:
                 logger.error(f"Unexpected state: Failed to get valid response for page {page} after retries.")
                 break

            try:
                data = response.json()
                lifelogs_data = data.get("data", {}).get("lifelogs", [])
                next_cursor = data.get("meta", {}).get("lifelogs", {}).get("nextCursor")

                if not lifelogs_data:
                    logger.info(f"No lifelogs found on page {page} for range {fetch_range_log}.")
                    break 
                
                logger.info(f"Fetched {len(lifelogs_data)} lifelogs on page {page}. Next cursor: {bool(next_cursor)}")

                for item in lifelogs_data:
                    start_time = _parse_iso_datetime(item.get("startTime"))
                    end_time = _parse_iso_datetime(item.get("endTime"))
                    lifelog_id = item.get("id")
                    content = item.get("markdown")
                    title = item.get("title")

                    if not lifelog_id or not content:
                         logger.warning(f"Skipping item due to missing ID or markdown: {item.get('id', 'N/A')}")
                         continue
                    
                    transcripts.append(
                        TranscriptCreate(
                            source="limitless",
                            source_id=lifelog_id,
                            title=title,
                            content=content,
                            start_time=start_time,
                            end_time=end_time,
                        )
                    )

                if not next_cursor:
                    logger.info(f"No next cursor provided by API for range {fetch_range_log}. Assuming end of data for this period.")
                    break
                
                cursor = next_cursor
                page += 1
                await asyncio.sleep(RATE_LIMIT_DELAY)

            except Exception as e:
                logger.error(f"Error processing response for page {page}: {e}", exc_info=True)
                break

    logger.info(f"Finished fetching for range {fetch_range_log}. Total transcripts retrieved: {len(transcripts)}")
    return transcripts 