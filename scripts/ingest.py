import asyncio
import argparse
import os
import logging
# No longer need sqlite3 here for timestamp check
from datetime import datetime, timedelta, timezone
from typing import Optional

from transcript_engine.core.config import Settings
from transcript_engine.ingest.ingest import ingest_transcripts
# No longer need CRUD functions here
# from transcript_engine.database.crud import get_latest_limitless_start_time, get_db 

logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Define the format required by the API (YYYY-MM-DD HH:MM:SS)
API_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
DEFAULT_FETCH_WINDOW_HOURS = 24 # Fetch the last 24 hours by default

def main():
    parser = argparse.ArgumentParser(
        description="Ingest recent transcripts from the Limitless API."
    )
    # Can add arguments for specific start/end times if needed later
    parser.add_argument(
        "--hours",
        type=int,
        default=DEFAULT_FETCH_WINDOW_HOURS,
        help=f"Number of hours back to fetch (default: {DEFAULT_FETCH_WINDOW_HOURS})."
    )
    parser.add_argument(
        "--timezone",
        type=str,
        default="UTC",
        help="IANA timezone specifier for API queries (default: UTC)."
    )
    args = parser.parse_args()

    settings = Settings()
    start_time_str: Optional[str] = None

    try:
        # Calculate start time based on the specified window
        now_utc = datetime.now(timezone.utc)
        fetch_since_time = now_utc - timedelta(hours=args.hours)
        start_time_str = fetch_since_time.strftime(API_DATETIME_FORMAT)
        logger.info(f"Fetching transcripts since {start_time_str} UTC ({args.hours} hours ago)...")

    except Exception as e:
        logger.error(f"Error calculating start time: {e}. Cannot proceed.", exc_info=True)
        return # Exit if we can't calculate the time

    # Run the ingestion process
    try:
        logger.info(f"Calling ingest_transcripts with start_time_iso='{start_time_str}'")
        ingested_count = asyncio.run(
            ingest_transcripts(
                settings=settings,
                start_time_iso=start_time_str, # Pass the calculated start time
                # end_time_iso is None (fetch up to current time)
                timezone=args.timezone,
            )
        )
        logger.info(f"Ingestion finished. Ingested {ingested_count} new transcripts.")
    except Exception as e:
        logger.error(f"Ingestion script failed: {e}", exc_info=True)


if __name__ == "__main__":
    main() 