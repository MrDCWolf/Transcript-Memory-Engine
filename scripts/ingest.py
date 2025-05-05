import asyncio
import argparse
import os
import logging
# No longer need sqlite3 here for timestamp check
from datetime import datetime, timedelta, timezone
from typing import Optional
from pathlib import Path # Add Path

from transcript_engine.core.config import Settings
from transcript_engine.ingest.ingest import ingest_transcripts
from transcript_engine.database.crud import (
    get_db,
    create_transcript,
    get_latest_limitless_start_time,
)
from transcript_engine.database.models import TranscriptCreate
from transcript_engine.interfaces.limitless import fetch_transcripts

logger = logging.getLogger(__name__)
# Use a more specific logger name if desired
# logger = logging.getLogger("ingest_script") 
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

# Define the format required by the API (YYYY-MM-DD HH:MM:SS)
# API_DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S" # No longer needed here
DEFAULT_FETCH_WINDOW_HOURS = 24 # Fetch the last 24 hours by default
DEFAULT_TIMEZONE = "UTC" # Default timezone for queries

# Directory to save raw responses
RAW_SAVE_DIR = Path("./data/raw_limitless_responses")

async def ingest_single_day(conn, target_date, timezone_str):
    """Fetches and ingests lifelogs for a single 24-hour period ending on target_date."""
    # Limitless API uses start (inclusive) and end (exclusive)
    # To get a full day, start at 00:00:00 and end at 00:00:00 of the *next* day
    day_start = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
    day_end = day_start + timedelta(days=1) 
    logger.info(f"--- Processing day: {day_start.date()} (Timezone: {timezone_str}) ---")
    
    try:
        # Ensure RAW_SAVE_DIR exists
        RAW_SAVE_DIR.mkdir(parents=True, exist_ok=True)
        
        # Fetch lifelogs, passing the save directory and timezone
        limitless_lifelogs = await fetch_transcripts(
            start_date=day_start, 
            end_date=day_end,
            timezone_str=timezone_str,
            save_dir=RAW_SAVE_DIR
        )
    except Exception as e:
        logger.error(f"Failed to fetch lifelogs for {day_start.date()}: {e}")
        return 0 # Return 0 ingested for this day on fetch error

    ingested_count = 0
    for log in limitless_lifelogs:
        # Extract data based on the /lifelogs response structure
        source_id = log.get("id")
        transcript_data = log.get("markdown")
        title = log.get("title", "Untitled Lifelog") # Use title if available
        start_time_str = log.get("startTime")
        end_time_str = log.get("endTime")
        
        # Basic validation
        if not source_id or transcript_data is None: # Check for None explicitly for markdown
            logger.warning(f"Skipping lifelog due to missing ID or markdown content: {log.get('id', 'N/A')}")
            continue
        
        # Parse timestamps (handle potential errors, assumes ISO format from API)
        try:
            start_time_dt = datetime.fromisoformat(start_time_str.replace('Z', '+00:00')) if start_time_str else None
            end_time_dt = datetime.fromisoformat(end_time_str.replace('Z', '+00:00')) if end_time_str else None
        except ValueError:
             logger.warning(f"Skipping lifelog {source_id} due to invalid timestamp format ('{start_time_str}' / '{end_time_str}').")
             continue
        
        transcript_to_create = TranscriptCreate(
            source="limitless",
            source_id=source_id,
            title=title,
            content=transcript_data, 
            start_time=start_time_dt, 
            end_time=end_time_dt 
        )

        try:
            create_transcript(conn, transcript_to_create)
            ingested_count += 1
        except sqlite3.IntegrityError:
            logger.debug(f"Lifelog with source_id '{source_id}' already exists. Skipping.")
        except Exception as e:
            logger.error(f"Failed to create transcript record for source_id '{source_id}': {e}", exc_info=True)
            
    logger.info(f"Ingested {ingested_count} new lifelogs for {day_start.date()}.")
    return ingested_count

async def backfill_transcripts(conn, timezone_str):
    """Performs backfilling day-by-day until no new lifelogs are found for several days."""
    logger.info(f"Starting Limitless transcript backfill (Timezone: {timezone_str})...")
    # Start checking from the beginning of today in the specified timezone
    try:
        from zoneinfo import ZoneInfo
        target_tz = ZoneInfo(timezone_str)
    except ImportError:
        logger.warning("zoneinfo module not available (Python < 3.9?), using UTC for backfill start.")
        target_tz = timezone.utc
    except Exception as e:
        logger.error(f"Invalid timezone '{timezone_str}' provided: {e}. Using UTC.")
        target_tz = timezone.utc
        
    current_check_date = datetime.now(target_tz).replace(hour=0, minute=0, second=0, microsecond=0)
    days_with_no_new = 0
    max_days_no_new = 5 # Stop after 5 consecutive days yield nothing

    while days_with_no_new < max_days_no_new:
        ingested = await ingest_single_day(conn, current_check_date, timezone_str)
        if ingested == 0:
            days_with_no_new += 1
        else:
            days_with_no_new = 0 # Reset counter if we found something
            
        # Move to the previous day
        current_check_date -= timedelta(days=1)
        # Don't need API delay here, fetch_transcripts has internal delay between pages
        
    logger.info(f"Backfill complete. Stopped after {max_days_no_new} consecutive days with no new lifelogs.")

async def ingest_recent_transcripts(conn, days: int, timezone_str: str):
    """Ingests lifelogs for the last N days."""
    logger.info(f"Starting ingestion for the last {days} day(s) (Timezone: {timezone_str})...")
    # Calculate start/end in UTC for the fetch call
    end_date_utc = datetime.now(timezone.utc)
    start_date_utc = end_date_utc - timedelta(days=days)
    
    # Ensure RAW_SAVE_DIR exists
    RAW_SAVE_DIR.mkdir(parents=True, exist_ok=True)

    logger.info(f"Fetching from {start_date_utc} to {end_date_utc}")
    try:
        limitless_lifelogs = await fetch_transcripts(
            start_date=start_date_utc, 
            end_date=end_date_utc,
            timezone_str=timezone_str,
            save_dir=RAW_SAVE_DIR
        )
    except Exception as e:
        logger.error(f"Failed to fetch recent lifelogs: {e}")
        return

    ingested_count = 0
    for log in limitless_lifelogs:
        source_id = log.get("id")
        transcript_data = log.get("markdown")
        title = log.get("title", "Untitled Lifelog")
        start_time_str = log.get("startTime")
        end_time_str = log.get("endTime")
        if not source_id or transcript_data is None:
            logger.warning(f"Skipping lifelog due to missing ID or markdown: {log.get('id', 'N/A')}")
            continue
        try:
            start_time_dt = datetime.fromisoformat(start_time_str.replace('Z', '+00:00')) if start_time_str else None
            end_time_dt = datetime.fromisoformat(end_time_str.replace('Z', '+00:00')) if end_time_str else None
        except ValueError:
             logger.warning(f"Skipping lifelog {source_id} due to invalid timestamp format.")
             continue
        transcript_to_create = TranscriptCreate(
            source="limitless", source_id=source_id, title=title,
            content=transcript_data, start_time=start_time_dt, end_time=end_time_dt
        )
        try:
            create_transcript(conn, transcript_to_create)
            ingested_count += 1
        except sqlite3.IntegrityError:
            logger.debug(f"Lifelog with source_id '{source_id}' already exists. Skipping.")
        except Exception as e:
            logger.error(f"Failed to create transcript record for source_id '{source_id}': {e}", exc_info=True)

    logger.info(f"Finished ingesting recent lifelogs. Added {ingested_count} new records.")

async def main_async(): # Rename original main to avoid conflict, make async
    parser = argparse.ArgumentParser(description="Ingest lifelogs from Limitless API.")
    parser.add_argument(
        "--backfill", 
        action="store_true", 
        help="Perform historical backfill day-by-day."
    )
    parser.add_argument(
        "--days",
        type=int,
        default=1,
        help="Number of recent days to fetch (default: 1). Ignored if --backfill is set."
    )
    parser.add_argument(
        "--start-date",
        type=str,
        help="Start date (YYYY-MM-DD) to fetch from. Fetches from this date up to now, ignoring --days and --backfill if set."
    )
    parser.add_argument(
        "--timezone",
        type=str,
        default=DEFAULT_TIMEZONE,
        help=f"IANA timezone specifier for API queries (default: {DEFAULT_TIMEZONE})."
    )

    args = parser.parse_args()

    db_conn = None # Initialize
    try:
        # Get the singleton connection instance directly
        db_conn = get_db() 

        if args.start_date:
            try:
                # Parse start date and make it timezone aware using the provided timezone
                try:
                    from zoneinfo import ZoneInfo
                    target_tz = ZoneInfo(args.timezone)
                except ImportError:
                    logger.warning("zoneinfo module not available (Python < 3.9?), using UTC.")
                    target_tz = timezone.utc
                except Exception as e:
                     logger.error(f"Invalid timezone '{args.timezone}' provided: {e}. Using UTC.")
                     target_tz = timezone.utc
                start_dt_naive = datetime.strptime(args.start_date, "%Y-%m-%d")
                start_dt = target_tz.localize(start_dt_naive) if hasattr(target_tz, 'localize') else start_dt_naive.replace(tzinfo=target_tz)
                
                # End date is now (in UTC for the API call)
                end_dt = datetime.now(timezone.utc) 
                
                logger.info(f"Fetching lifelogs from {start_dt.date()} ({args.timezone}) to now.")
                
                # Ensure RAW_SAVE_DIR exists
                RAW_SAVE_DIR.mkdir(parents=True, exist_ok=True)
                
                # Fetch and save
                limitless_lifelogs = await fetch_transcripts(
                    start_date=start_dt.astimezone(timezone.utc), # Convert to UTC for API if needed?
                    end_date=end_dt, 
                    timezone_str=args.timezone,
                    save_dir=RAW_SAVE_DIR
                )
                
                # Process fetched events (similar loop as ingest_recent_transcripts)
                ingested_count = 0
                for log in limitless_lifelogs:
                    source_id = log.get("id")
                    transcript_data = log.get("markdown")
                    title = log.get("title", "Untitled Lifelog")
                    start_time_str = log.get("startTime")
                    end_time_str = log.get("endTime")
                    if not source_id or transcript_data is None:
                        logger.warning(f"Skipping lifelog due to missing ID or markdown: {log.get('id', 'N/A')}")
                        continue
                    try:
                        start_time_dt = datetime.fromisoformat(start_time_str.replace('Z', '+00:00')) if start_time_str else None
                        end_time_dt = datetime.fromisoformat(end_time_str.replace('Z', '+00:00')) if end_time_str else None
                    except ValueError:
                         logger.warning(f"Skipping lifelog {source_id} due to invalid timestamp format.")
                         continue
                    transcript_to_create = TranscriptCreate(
                        source="limitless", source_id=source_id, title=title,
                        content=transcript_data, start_time=start_time_dt, end_time=end_time_dt
                    )
                    try:
                        create_transcript(db_conn, transcript_to_create)
                        ingested_count += 1
                    except sqlite3.IntegrityError:
                        logger.debug(f"Lifelog with source_id '{source_id}' already exists. Skipping.")
                    except Exception as e:
                        logger.error(f"Failed to create transcript record for source_id '{source_id}': {e}", exc_info=True)
                logger.info(f"Finished ingesting from start date. Added {ingested_count} new records.")
                
            except ValueError as e:
                 logger.error(f"Invalid format for --start-date (Use YYYY-MM-DD) or error during processing: {e}")
                 return
                 
        elif args.backfill:
            await backfill_transcripts(db_conn, args.timezone)
        else:
            await ingest_recent_transcripts(db_conn, days=args.days, timezone_str=args.timezone)
            
    except Exception as e:
        logger.critical(f"An error occurred during the ingestion process: {e}", exc_info=True)
    finally:
        # Let the main application handle connection closing via lifespan
        if db_conn:
             logger.debug("Script finished. DB connection will be managed by application lifecycle or OS.")
             pass

if __name__ == "__main__":
    # Add import for sqlite3 if not already present
    import sqlite3 
    # Use the async main function
    asyncio.run(main_async()) 