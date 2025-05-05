from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any, Optional
import httpx
import logging
import time
import os
from pathlib import Path
import json
import asyncio

from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

BASE_URL = "https://api.limitless.ai/v1"
LIFELOGS_ENDPOINT = "/lifelogs"
API_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"

def get_limitless_api_key() -> str | None:
    return os.getenv("LIMITLESS_API_KEY")

@retry(
    stop=stop_after_attempt(5),
    wait=wait_exponential(multiplier=1, min=2, max=30),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.HTTPStatusError)),
    reraise=True
)
async def _fetch_single_page(
    client: httpx.AsyncClient,
    api_key: str,
    params: Dict[str, Any]
) -> Dict[str, Any]:
    headers = {
        "X-API-Key": api_key,
        "Accept": "application/json"
    }
    url = f"{BASE_URL}{LIFELOGS_ENDPOINT}"
    
    logger.debug(f"Fetching Limitless page with params: {params}")
    response = await client.get(url, headers=headers, params=params)
    
    if 500 <= response.status_code < 600:
        logger.warning(f"Received {response.status_code} from Limitless API. Retrying...")
        response.raise_for_status()
        
    response.raise_for_status()
    
    return response.json()

async def fetch_transcripts(
    start_date: datetime,
    end_date: datetime,
    timezone_str: str = "UTC",
    save_dir: Optional[Path | str] = None
) -> List[Dict[str, Any]]:
    api_key = get_limitless_api_key()
    if not api_key:
        logger.error("Limitless API key not found (LIMITLESS_API_KEY).")
        raise ValueError("Missing Limitless API key.")

    all_lifelogs = []
    all_raw_responses = []
    next_cursor = None
    page_count = 0

    start_str = start_date.strftime(API_DATETIME_FORMAT)
    end_str = end_date.strftime(API_DATETIME_FORMAT)

    logger.info(f"Fetching Limitless lifelogs from {start_str} to {end_str} (Timezone: {timezone_str})...")
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        while True:
            page_count += 1
            params = {
                "start": start_str,
                "end": end_str,
                "timezone": timezone_str,
                "limit": 10,
                "direction": "asc",
                "includeMarkdown": True,
            }
            if next_cursor:
                params["cursor"] = next_cursor

            try:
                raw_json_data = await _fetch_single_page(client, api_key, params)
                if save_dir: 
                    all_raw_responses.append(raw_json_data)

                page_lifelogs = raw_json_data.get("data", {}).get("lifelogs", [])
                if not isinstance(page_lifelogs, list):
                    logger.warning(f"Limitless API response page {page_count} did not contain a list under 'data.lifelogs'. Response: {raw_json_data}")
                    break
                
                all_lifelogs.extend(page_lifelogs)
                logger.info(f"Fetched page {page_count} with {len(page_lifelogs)} lifelogs.")

                next_cursor = raw_json_data.get("meta", {}).get("lifelogs", {}).get("nextCursor")
                if not next_cursor or not page_lifelogs:
                    break
                
                await asyncio.sleep(0.5)

            except httpx.HTTPStatusError as e:
                logger.error(f"HTTP error fetching Limitless page {page_count}: {e.response.status_code} - {e.response.text}", exc_info=True)
                raise 
            except Exception as e:
                logger.error(f"Unexpected error fetching Limitless page {page_count}: {e}", exc_info=True)
                raise
                
    logger.info(f"Successfully fetched a total of {len(all_lifelogs)} lifelogs across {page_count} page(s).")

    if save_dir and all_raw_responses:
        try:
            save_dir = Path(save_dir)
            save_dir.mkdir(parents=True, exist_ok=True)
            filename = f"limitless_{end_date.strftime('%Y-%m-%d_%H%M%S')}.json"
            filepath = save_dir / filename
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(all_raw_responses, f, ensure_ascii=False, indent=4)
            logger.info(f"Saved combined raw Limitless responses ({len(all_raw_responses)} pages) to {filepath}")
        except Exception as save_e:
            logger.error(f"Failed to save combined raw Limitless response: {save_e}", exc_info=True)

    return all_lifelogs 