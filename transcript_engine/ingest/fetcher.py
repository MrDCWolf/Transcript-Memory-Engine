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

async def fetch_transcripts(
    api_key: str,
    start_date: str | None = None,
    end_date: str | None = None,
    timezone: str = "UTC",
) -> list[TranscriptCreate]:
    """Fetch transcripts from the Limitless API.

    Args:
        api_key: The Limitless API key.
        start_date: Start date in YYYY-MM-DD format. If None, fetches all available.
        end_date: End date in YYYY-MM-DD format. If None, uses current date.
        timezone: IANA timezone specifier. Defaults to UTC.

    Returns:
        List of TranscriptCreate objects.
    """
    base_url = "https://api.limitless.ai/v1/lifelogs"
    headers = {"X-API-Key": api_key}
    transcripts = []
    cursor = None

    async with httpx.AsyncClient() as client:
        while True:
            params = {
                "timezone": timezone,
                "includeMarkdown": "true",
                "includeHeadings": "true",
                "limit": "10",
                "direction": "desc",  # Get most recent first
            }
            if start_date:
                params["start"] = start_date
            if end_date:
                params["end"] = end_date
            if cursor:
                params["cursor"] = cursor

            try:
                response = await client.get(base_url, headers=headers, params=params)
                response.raise_for_status()
                data = response.json()

                for item in data["data"]["lifelogs"]:
                    # Parse ISO-8601 timestamps
                    start_time = (
                        datetime.fromisoformat(item["startTime"].replace("Z", "+00:00"))
                        if item.get("startTime")
                        else None
                    )
                    end_time = (
                        datetime.fromisoformat(item["endTime"].replace("Z", "+00:00"))
                        if item.get("endTime")
                        else None
                    )

                    transcripts.append(
                        TranscriptCreate(
                            title=item["title"],
                            content=item["markdown"],
                            start_time=start_time,
                            end_time=end_time,
                        )
                    )

                cursor = data["meta"]["lifelogs"].get("nextCursor")
                if not cursor:
                    break

            except httpx.RequestError as e:
                logger.error(f"Request failed: {e}")
                break
            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error: {e}")
                break
            except Exception as e:
                logger.error(f"Unexpected error: {e}")
                break

    return transcripts 