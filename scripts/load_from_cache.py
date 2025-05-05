"""Script to load transcript data from locally cached Limitless JSON files.

Reads the latest JSON file found in the cache directory and populates the database.
Does NOT call the Limitless API.
"""

import asyncio
import argparse
import logging
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Dict, Any

# Need to adjust path if script is run from root vs. inside scripts/
# Assuming run from root: poetry run python -m scripts.load_from_cache
from transcript_engine.database.crud import (
    get_db,
    add_transcripts_batch,
)
from transcript_engine.database.models import TranscriptCreate

# Configure logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

# Directory where raw responses are saved
CACHE_DIR = Path("./data/raw_limitless_responses")
BATCH_SIZE = 1000 # Process 1000 transcripts at a time

def find_latest_cache_file(directory: Path) -> Path | None:
    """Finds the most recently modified JSON file in the directory."""
    try:
        json_files = list(directory.glob("limitless_*.json"))
        if not json_files:
            return None
        # Sort by modification time, descending
        latest_file = max(json_files, key=lambda p: p.stat().st_mtime)
        return latest_file
    except FileNotFoundError:
        return None
    except Exception as e:
        logger.error(f"Error finding latest cache file in {directory}: {e}", exc_info=True)
        return None

def prepare_transcripts(lifelogs: List[Dict[str, Any]]) -> tuple[List[TranscriptCreate], int]:
    """Converts lifelogs into TranscriptCreate objects, skipping invalid ones.
    
    Returns: Tuple of (List[TranscriptCreate], skipped_count)
    """
    transcripts_to_create: List[TranscriptCreate] = []
    skipped_count = 0
    for log in lifelogs:
        source_id = log.get("id")
        transcript_data = log.get("markdown")
        title = log.get("title", "Untitled Lifelog")
        start_time_str = log.get("startTime")
        end_time_str = log.get("endTime")

        if not source_id or transcript_data is None:
            logger.warning(f"Skipping cached lifelog due to missing ID/markdown: {log.get('id', 'N/A')}")
            skipped_count += 1
            continue

        try:
            start_time_dt = datetime.fromisoformat(start_time_str.replace('Z', '+00:00')) if start_time_str else None
            end_time_dt = datetime.fromisoformat(end_time_str.replace('Z', '+00:00')) if end_time_str else None
            # Ensure start_time is present for our date query logic later
            if start_time_dt is None:
                 logger.warning(f"Skipping cached lifelog {source_id} due to missing startTime.")
                 skipped_count += 1
                 continue
        except ValueError:
             logger.warning(f"Skipping cached lifelog {source_id} due to invalid timestamp format.")
             skipped_count += 1
             continue
        
        transcripts_to_create.append(
             TranscriptCreate(
                source="limitless",
                source_id=source_id,
                title=title,
                content=transcript_data, 
                start_time=start_time_dt, 
                end_time=end_time_dt 
            )
        )
    return transcripts_to_create, skipped_count

async def main_async():
    logger.info(f"--- Starting Load from Cache Script (Batch Size: {BATCH_SIZE}) ---")
    
    cache_file = find_latest_cache_file(CACHE_DIR)
    if not cache_file:
        logger.error(f"No cache files found in {CACHE_DIR}. Cannot proceed.")
        return

    logger.info(f"Processing latest cache file: {cache_file.name}")

    db_conn = None
    total_lifelogs_found = 0
    total_prepared = 0
    total_ingested = 0 # Actual rows inserted (ignoring duplicates)
    total_skipped_validation = 0
    total_batches_processed = 0

    try:
        db_conn = get_db() # Get the shared DB connection
        
        logger.info(f"Reading and parsing cache file: {cache_file}")
        all_lifelogs = []
        with open(cache_file, 'r', encoding='utf-8') as f:
            raw_page_responses = json.load(f)
            if not isinstance(raw_page_responses, list):
                 logger.error(f"Cache file {cache_file.name} does not contain a list. Aborting.")
                 return
            for page_response in raw_page_responses:
                 page_lifelogs = page_response.get("data", {}).get("lifelogs", [])
                 all_lifelogs.extend(page_lifelogs)
        
        total_lifelogs_found = len(all_lifelogs)
        logger.info(f"Found {total_lifelogs_found} total lifelogs in cache file.")

        if not all_lifelogs:
             logger.info("No lifelogs to process.")
             return

        logger.info("Preparing transcript objects...")
        transcripts_to_create, skipped_validation = prepare_transcripts(all_lifelogs)
        total_skipped_validation = skipped_validation
        total_prepared = len(transcripts_to_create)
        logger.info(f"Prepared {total_prepared} valid transcripts for insertion. Skipped {total_skipped_validation} due to validation errors.")

        if not transcripts_to_create:
            logger.info("No valid transcripts prepared for database insertion.")
            return

        logger.info("Starting batch insertion into database...")
        for i in range(0, total_prepared, BATCH_SIZE):
            batch = transcripts_to_create[i : i + BATCH_SIZE]
            batch_num = (i // BATCH_SIZE) + 1
            logger.info(f"Processing batch {batch_num}/{((total_prepared - 1) // BATCH_SIZE) + 1} (size: {len(batch)})...")
            try:
                inserted_count = add_transcripts_batch(db_conn, batch)
                total_ingested += inserted_count
                total_batches_processed += 1
            except sqlite3.Error as e:
                # Log error but continue to next batch if possible, 
                # as some rows in the failed batch might have been duplicates anyway if using INSERT OR IGNORE
                logger.error(f"Database error processing batch {batch_num}: {e}", exc_info=True)
                # Depending on error, might want to stop entirely
                # For now, we log and continue
        
        logger.info(f"--- Load from Cache Summary ---")
        logger.info(f"Processed file: {cache_file.name}")
        logger.info(f"Total lifelogs found: {total_lifelogs_found}")
        logger.info(f"Skipped during validation: {total_skipped_validation}")
        logger.info(f"Prepared for insertion: {total_prepared}")
        logger.info(f"Batches processed: {total_batches_processed}")
        logger.info(f"Rows actually inserted/affected (using INSERT OR IGNORE): {total_ingested}")

    except FileNotFoundError:
        logger.error(f"Cache file {cache_file} not found during processing.")
    except json.JSONDecodeError:
        logger.error(f"Error decoding JSON from cache file {cache_file}. Is it corrupted?")
    except Exception as e:
        logger.critical(f"An unexpected error occurred during the cache loading process: {e}", exc_info=True)
    finally:
        logger.info("Cache loading script finished.")

if __name__ == "__main__":
    # Need to import config for the init check
    from transcript_engine.core.config import get_settings, Settings 
    from transcript_engine.database.crud import initialize_database
    from pathlib import Path
    import logging # Make sure logging is available here too
    logger = logging.getLogger(__name__) # Re-get logger for this scope

    # Need to initialize the database explicitly if this script runs standalone
    # because get_db() might rely on lifespan otherwise.
    try:
        logger.info("Ensuring database schema exists before loading...")
        settings = get_settings() # Load settings to find DB path
        db_url = settings.database_url
        # Correct path handling
        if not db_url.startswith("sqlite:///"):
             raise ValueError(f"Invalid database_url format: {db_url}. Expected 'sqlite:///path/to/db.sqlite'")
        db_path_str = db_url[len("sqlite:///"):]
        db_path = Path(db_path_str).resolve()

        initialize_database(db_path)
        logger.info("Database schema check complete.")
    except Exception as init_e:
        logger.critical(f"Failed to initialize database schema before loading: {init_e}", exc_info=True)
        exit(1) # Stop if DB can't be initialized

    asyncio.run(main_async()) 