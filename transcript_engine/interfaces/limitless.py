"""Interface and implementation for fetching data from the Limitless API."""

from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional, Protocol, AsyncGenerator
import httpx
import logging
import time
import os
from pathlib import Path
import json
import asyncio

from pydantic import BaseModel
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

# --- Data Models --- 

class TranscriptData(BaseModel):
    source: str = "limitless"
    source_id: str
    title: Optional[str] = None
    content: Optional[str] = None # Expected to be markdown
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    # Add other relevant fields from Limitless lifelog if needed
    raw_data: Optional[Dict[str, Any]] = None # Store original response

# --- Interface Protocol --- 

class LimitlessInterface(Protocol):
    """Interface for fetching transcripts from Limitless API."""
    async def fetch_transcripts(self, since: Optional[datetime] = None) -> AsyncGenerator[TranscriptData, None]:
        """Fetches transcripts from Limitless API, starting from a given time.

        Args:
            since: If provided, fetch transcripts with start_time >= since.
                   If None, fetch all available (or a default recent range).

        Yields:
            TranscriptData: Individual transcript data objects.
        """
        ...

# --- Implementation --- 

class LimitlessAPIClient(LimitlessInterface):
    """Concrete implementation for fetching data from Limitless API."""
    
    BASE_URL = "https://api.limitless.ai/v1"
    LIFELOGS_ENDPOINT = "/lifelogs"
    API_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S" # Limitless API uses this format
    PAGE_LIMIT = 50 # Increase limit for efficiency
    RETRY_MAX_ATTEMPTS = 5
    RETRY_WAIT_MULTIPLIER = 1 # Keeps wait times increasing linearly rather than truly exponentially
    RETRY_WAIT_MIN = 10 # Increased initial wait to 10 seconds
    RETRY_WAIT_MAX = 60 # Increased max wait to 60 seconds
    REQUEST_TIMEOUT = 60.0 # Increased timeout
    DEFAULT_TIMEZONE = "UTC"

    def __init__(self, api_key: Optional[str] = None, save_dir: Optional[Path | str] = None):
        self.api_key = api_key or os.getenv("LIMITLESS_API_KEY")
        if not self.api_key:
            logger.error("Limitless API key not found (env var LIMITLESS_API_KEY or passed explicitly).")
            raise ValueError("Missing Limitless API key.")
            
        self.save_dir = Path(save_dir) if save_dir else None
        if self.save_dir:
             self.save_dir.mkdir(parents=True, exist_ok=True)
             logger.info(f"Raw Limitless responses will be saved to: {self.save_dir}")
             
        self.http_client = httpx.AsyncClient(timeout=self.REQUEST_TIMEOUT)

    async def close(self):
        """Close the underlying HTTP client."""
        await self.http_client.aclose()
        logger.info("Limitless HTTP client closed.")

    @retry(
        stop=stop_after_attempt(RETRY_MAX_ATTEMPTS),
        wait=wait_exponential(multiplier=RETRY_WAIT_MULTIPLIER, min=RETRY_WAIT_MIN, max=RETRY_WAIT_MAX),
        retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
        reraise=True
    )
    async def _fetch_single_page(
        self,
        params: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Fetches a single page of lifelogs with retry logic."""
        headers = {
            "X-API-Key": self.api_key,
            "Accept": "application/json"
        }
        url = f"{self.BASE_URL}{self.LIFELOGS_ENDPOINT}"
        
        logger.debug(f"Fetching Limitless page with params: {params}")
        response = await self.http_client.get(url, headers=headers, params=params)
        
        if 500 <= response.status_code < 600:
            logger.warning(f"Received {response.status_code} from Limitless API. Retrying...")
            response.raise_for_status()
            
        response.raise_for_status()
        return response.json()

    async def fetch_transcripts(self, since: Optional[datetime] = None) -> AsyncGenerator[TranscriptData, None]:
        """Fetches transcripts from Limitless API asynchronously, yielding TranscriptData objects."""
        
        # Default to fetching last 24 hours if no specific start time
        end_date = datetime.now(timezone.utc)
        start_date = since or (end_date - timedelta(days=1))
        
        # Ensure dates are timezone-aware (UTC assumed)
        if start_date.tzinfo is None:
             start_date = start_date.replace(tzinfo=timezone.utc)
        if end_date.tzinfo is None:
             end_date = end_date.replace(tzinfo=timezone.utc)

        start_str = start_date.strftime(self.API_DATETIME_FORMAT)
        end_str = end_date.strftime(self.API_DATETIME_FORMAT)

        logger.info(f"Fetching Limitless lifelogs from {start_str} to {end_str} (Timezone: {self.DEFAULT_TIMEZONE})...")
        
        next_cursor = None
        page_count = 0
        total_lifelogs_processed = 0
        
        while True:
            page_count += 1
            params = {
                "start": start_str,
                "end": end_str,
                "timezone": self.DEFAULT_TIMEZONE,
                "limit": self.PAGE_LIMIT,
                "direction": "asc",
                "includeMarkdown": True,
            }
            if next_cursor:
                params["cursor"] = next_cursor

            try:
                raw_json_data = await self._fetch_single_page(params=params)
                page_lifelogs = raw_json_data.get("data", {}).get("lifelogs", [])
                
                if not isinstance(page_lifelogs, list):
                    logger.warning(f"Limitless API response page {page_count} did not contain a list under 'data.lifelogs'. Response: {raw_json_data}")
                    break
                
                logger.info(f"Processing page {page_count} with {len(page_lifelogs)} lifelogs.")
                
                for lifelog in page_lifelogs:
                    total_lifelogs_processed += 1
                    try:
                         start_time = datetime.fromisoformat(lifelog['startTime']) if lifelog.get('startTime') else None
                         end_time = datetime.fromisoformat(lifelog['endTime']) if lifelog.get('endTime') else None
                         
                         # Skip if start_time is before the requested 'since' time (API might return overlapping ranges)
                         if since and start_time and start_time < since:
                             continue

                         # --- Assemble content from blockquotes ---
                         assembled_content = "" # Initialize outside the loop
                         if 'contents' in lifelog and isinstance(lifelog['contents'], list):
                             for block in lifelog['contents']:
                                 # Ensure block is a dictionary before accessing keys
                                 if isinstance(block, dict) and block.get('type') == 'blockquote':
                                     # Get speaker and text safely
                                     speaker = block.get('speakerName', 'Unknown')
                                     text = block.get('content', '').strip()
                                     
                                     # Only process if text is not empty after stripping
                                     if text:
                                         # Ensure this line has the correct indentation relative to the 'if text:'
                                         assembled_content += f'{speaker}: {text}\n' # Combined f-string and newline

                         # Use assembled content, fallback to None if empty after stripping
                         transcript_content = assembled_content.strip() if assembled_content else None
                         # -----------------------------------------

                         yield TranscriptData(
                             source_id=lifelog['id'],
                             title=lifelog.get('title'),
                             # Use the newly assembled content
                             content=transcript_content,
                             start_time=start_time,
                             end_time=end_time,
                             raw_data=lifelog # Store original data if needed
                         )
                    except (KeyError, ValueError) as e:
                        logger.warning(f"Could not process lifelog {lifelog.get('id', 'N/A')} due to parsing error: {e} - Skipping. Data: {lifelog}")
                        continue 
                        
                next_cursor = raw_json_data.get("meta", {}).get("lifelogs", {}).get("nextCursor")
                if not next_cursor or not page_lifelogs:
                    break # Exit loop if no next page or page was empty
                
                await asyncio.sleep(0.2) # Small delay between page fetches

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching Limitless page {page_count}: {e.response.status_code} - {e.response.text}", exc_info=True)
                raise # Re-raise after logging
            except Exception as e:
                logger.error(f"Unexpected error fetching/processing Limitless page {page_count}: {e}", exc_info=True)
                raise # Re-raise after logging
                
        logger.info(f"Completed fetching Limitless lifelogs. Processed {total_lifelogs_processed} items across {page_count} page(s).")

# --- Removed old fetch_transcripts function --- 