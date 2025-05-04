"""Script to fetch transcripts from the source and store them in the database.
"""

import logging
import sqlite3
from datetime import date
import sys
import os

# Ensure the main package is in the Python path
# This allows running the script directly while using package imports
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from transcript_engine.core.config import get_settings, Settings
from transcript_engine.database import crud
from transcript_engine.ingest.fetcher import fetch_transcripts
from transcript_engine.database.crud import initialize_database # Needed if run standalone

# --- Logging Setup --- (Consider moving to a shared core.logging module)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
# --- End Logging Setup ---

def main():
    """Main function to run the transcript ingestion process.
    """
    logger.info("Starting transcript ingestion process...")
    settings = get_settings()
    
    conn = None # Initialize conn to None
    try:
        # --- Database Connection --- 
        # Manually connect as we are outside FastAPI dependency injection
        db_path_relative = settings.database_url.split("///")[-1]
        db_path_absolute = os.path.join(project_root, db_path_relative)
        os.makedirs(os.path.dirname(db_path_absolute), exist_ok=True)
        conn = sqlite3.connect(db_path_absolute)
        conn.row_factory = sqlite3.Row
        logger.info(f"Connected to database: {db_path_absolute}")

        # Initialize DB (in case it wasn't done by API startup)
        initialize_database(conn)
        # -------------------------

        # Get timestamp of the latest transcript already in DB
        latest_timestamp = crud.get_latest_transcript_timestamp(conn)
        since_date: date | None = None
        if latest_timestamp:
            since_date = latest_timestamp.date()
            logger.info(f"Fetching transcripts created since: {since_date}")
        else:
            logger.info("No existing transcripts found. Fetching all available transcripts.")

        # Fetch transcripts from the source (using placeholder function for now)
        # TODO: Add real API URL and Key to .env and Settings model
        api_url = getattr(settings, 'transcript_api_url', "http://dummy.invalid/api")
        api_key = getattr(settings, 'transcript_api_key', None)
        
        fetched_transcripts = fetch_transcripts(
            api_url=api_url, 
            api_key=api_key, 
            since_date=since_date
        )

        if not fetched_transcripts:
            logger.info("No new transcripts fetched.")
            return

        logger.info(f"Fetched {len(fetched_transcripts)} potential new transcripts.")

        # Add fetched transcripts to the database
        added_count = 0
        skipped_count = 0
        error_count = 0
        
        for transcript_data in fetched_transcripts:
            try:
                crud.create_transcript(conn=conn, transcript=transcript_data)
                added_count += 1
            except sqlite3.IntegrityError:
                # Transcript with this source_id already exists
                logger.debug(f"Skipping duplicate transcript with source_id: {transcript_data.source_id}")
                skipped_count += 1
            except sqlite3.Error as e:
                logger.error(
                    f"Database error adding transcript source_id {transcript_data.source_id}: {e}", 
                    exc_info=True
                )
                error_count += 1
            except Exception as e:
                 logger.error(
                    f"Unexpected error adding transcript source_id {transcript_data.source_id}: {e}", 
                    exc_info=True
                )
                 error_count += 1

        logger.info("Ingestion process finished.")
        logger.info(f"Summary: Added={added_count}, Skipped={skipped_count}, Errors={error_count}")

    except Exception as e:
        logger.critical(f"An critical error occurred during ingestion: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed.")

if __name__ == "__main__":
    main() 