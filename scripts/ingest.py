import asyncio
import argparse
import os
import logging
# No longer need sqlite3 here for timestamp check
from datetime import datetime, timedelta, timezone
from typing import Optional
from pathlib import Path # Add Path

from transcript_engine.core.config import Settings, get_settings # Import get_settings
from transcript_engine.ingest.ingest import ingest_transcripts # This seems unused now?
from transcript_engine.database.crud import (
    get_db,
    create_transcript,
    get_latest_limitless_start_time, # Likely also unused if we clear DB
    initialize_database,
)
from transcript_engine.database.models import TranscriptCreate
# Import the Client instead of the old function
from transcript_engine.interfaces.limitless import LimitlessAPIClient, TranscriptData 

logger = logging.getLogger(__name__)
# Use a more specific logger name if desired
# logger = logging.getLogger("ingest_script") 
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Directory where raw responses are saved
RAW_SAVE_DIR = Path("./data/raw_limitless_responses")
# Removed DEFAULT_FETCH_WINDOW_HOURS and DEFAULT_TIMEZONE as client/args handle defaults


# Removed old ingest_single_day function as client handles pagination
# Removed old backfill_transcripts function
# Removed old ingest_recent_transcripts function

async def main_async():
    parser = argparse.ArgumentParser(description="Ingest lifelogs from Limitless API.")
    # Keep args, but simplify logic
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date (YYYY-MM-DD) to fetch from. Fetches from this date up to now."
    )
    # Client uses UTC by default, timezone arg may not be needed unless API supports it differently?
    # Let's remove it for now for simplicity, relying on UTC.
    # parser.add_argument(
    #     "--timezone",
    #     type=str,
    #     default="UTC",
    #     help=f"IANA timezone specifier for API queries (default: UTC)."
    # )

    args = parser.parse_args()

    db_conn = None
    limitless_client = None
    try:
        # Get settings for API key and save dir
        settings = get_settings()
        
        # Get DB connection (before client)
        db_conn = get_db()
        
        # --- Initialize Database Schema --- 
        try:
            db_url = settings.database_url
            if not db_url.startswith("sqlite:///"):
                 raise ValueError(f"Invalid database_url format: {db_url}.")
            db_path_str = db_url[len("sqlite:///"):]
            db_path = Path(db_path_str).resolve()
            initialize_database(db_path) # Initialize using the path
            logger.info("Database schema initialized/verified.")
        except Exception as init_e:
            logger.critical(f"Failed to initialize database schema: {init_e}", exc_info=True)
            # Close client if already opened, though we moved DB connection earlier
            if limitless_client:
                 await limitless_client.close()
            return # Exit if DB init fails
        # ---------------------------------

        # Ensure RAW_SAVE_DIR exists
        RAW_SAVE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Instantiate the client
        # The client reads API key from env var LIMITLESS_API_KEY
        # Pass the save_dir to ensure raw responses are cached
        limitless_client = LimitlessAPIClient(save_dir=RAW_SAVE_DIR)
        
        # Determine start_dt for the client call
        start_dt: Optional[datetime] = None
        if args.start_date:
            try:
                # Parse start date and make it timezone aware UTC
                start_dt_naive = datetime.strptime(args.start_date, "%Y-%m-%d")
                start_dt = start_dt_naive.replace(tzinfo=timezone.utc)
                logger.info(f"Fetching lifelogs starting from {start_dt.date()} UTC up to now.")
            except ValueError:
                 logger.error(f"Invalid format for --start-date (Use YYYY-MM-DD).")
                 return
        else:
            # Default: Fetch last 24 hours (or whatever the client defaults to)
            logger.info(f"No --start-date specified. Fetching default range (likely last 24h).")
            # Pass None to client.fetch_transcripts, it handles the default
        
        ingested_count = 0
        
        # Use the client's fetch_transcripts method (async generator)
        async for transcript_data in limitless_client.fetch_transcripts(since=start_dt):
            # transcript_data is already a TranscriptData object
            
            # --- Log content for debugging ---
            if transcript_data.content is None or len(transcript_data.content.strip()) == 0:
                 logger.warning(f"TranscriptData source_id '{transcript_data.source_id}' has None or empty content.")
            else:
                 logger.debug(f"TranscriptData source_id '{transcript_data.source_id}' content length: {len(transcript_data.content)}")
            # ---------------------------------
            
            # We need to convert it to TranscriptCreate for the DB function
            transcript_to_create = TranscriptCreate(
                source=transcript_data.source,
                source_id=transcript_data.source_id,
                title=transcript_data.title,
                content=transcript_data.content, 
                start_time=transcript_data.start_time, 
                end_time=transcript_data.end_time 
            )
            
            # Attempt to insert into DB
            try:
                create_transcript(db_conn, transcript_to_create)
                ingested_count += 1
                if ingested_count % 100 == 0:
                     logger.info(f"Ingested {ingested_count} transcripts so far...")
            except sqlite3.IntegrityError:
                logger.debug(f"Lifelog with source_id '{transcript_to_create.source_id}' already exists. Skipping.")
            except Exception as e:
                logger.error(f"Failed to create transcript record for source_id '{transcript_to_create.source_id}': {e}", exc_info=True)

        logger.info(f"Finished ingestion. Added {ingested_count} new records.")
                
    except Exception as e:
        logger.critical(f"An error occurred during the ingestion process: {e}", exc_info=True)
    finally:
        # Close the HTTP client gracefully
        if limitless_client:
            await limitless_client.close()
        # DB connection is managed elsewhere (lifespan)
        logger.debug("Ingest script finished.")

if __name__ == "__main__":
    # Add import for sqlite3 if not already present
    import sqlite3 
    # Use the async main function
    asyncio.run(main_async()) 