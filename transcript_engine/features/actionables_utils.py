# This file will contain utility functions for the actionable items feature. 

import sqlite3
import logging
from datetime import date, datetime, timedelta, timezone
from typing import List, Optional

from transcript_engine.database import crud
from transcript_engine.database.models import Chunk, Transcript
from transcript_engine.core.config import get_settings

logger = logging.getLogger(__name__)

def get_transcript_for_timeframe(
    db: sqlite3.Connection, target_date: date, timeframe_key: str
) -> Optional[str]:
    """
    Fetches and filters transcript content for a given date and timeframe.

    This function retrieves all transcripts that overlap with the target_date.
    Then, it collects all chunks from these transcripts.
    Each chunk's absolute start time is calculated using its parent transcript's 
    start_time and the chunk's own relative start_time (offset in seconds).
    Chunks are then filtered if their absolute start time falls within the 
    specified timeframe (morning, afternoon, evening) on the target_date.
    The content of these filtered chunks is concatenated and returned.

    Args:
        db: An active sqlite3 database connection.
        target_date: The specific date for which to retrieve content.
        timeframe_key: A string key representing the timeframe 
                       (e.g., "morning", "afternoon", "evening").
                       Must be a key in settings.TIMEFRAME_BOUNDARIES.

    Returns:
        A string containing the concatenated content of all chunks within the 
        specified date and timeframe, or None if no relevant chunks are found
        or if the timeframe_key is invalid.
    """
    settings = get_settings()
    if timeframe_key not in settings.TIMEFRAME_BOUNDARIES:
        logger.error(f"Invalid timeframe_key: {timeframe_key}")
        return None

    timeframe_start_hour, timeframe_end_hour = settings.TIMEFRAME_BOUNDARIES[timeframe_key]

    # Define the full day for the target_date in UTC
    day_start_dt = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=timezone.utc)
    day_end_dt = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)

    logger.debug(f"Fetching transcript IDs for date: {target_date} (Full day: {day_start_dt} to {day_end_dt})")
    
    try:
        # Get all transcript IDs that overlap with the target_date
        # crud.get_transcript_ids_by_date_range expects start and end datetimes.
        transcript_ids = crud.get_transcript_ids_by_date_range(db, day_start_dt, day_end_dt)
        if not transcript_ids:
            logger.info(f"No transcripts found for date {target_date}")
            return "" # Return empty string if no transcripts for the day

        relevant_chunks_content: List[str] = []
        
        # Define the target timeframe window for the specific target_date
        # Make sure to use UTC for comparison if transcript.start_time is UTC
        timeframe_window_start = datetime(target_date.year, target_date.month, target_date.day, timeframe_start_hour, 0, 0, tzinfo=timezone.utc)
        # timeframe_end_hour is exclusive, so if it's 12, it means up to 11:59:59.999...
        # If end_hour is 24, it means up to 23:59:59.999...
        if timeframe_end_hour == 24:
             timeframe_window_end = datetime(target_date.year, target_date.month, target_date.day, 23, 59, 59, 999999, tzinfo=timezone.utc)
        else:
             timeframe_window_end = datetime(target_date.year, target_date.month, target_date.day, timeframe_end_hour, 0, 0, tzinfo=timezone.utc)


        logger.debug(f"Processing {len(transcript_ids)} transcript(s) for {target_date}.")
        logger.debug(f"Target timeframe '{timeframe_key}': {timeframe_window_start.time()} to {timeframe_window_end.time()} (exclusive end for hour {timeframe_end_hour})")

        for t_id in transcript_ids:
            transcript: Optional[Transcript] = crud.get_transcript_by_id(db, t_id)
            if not transcript or not transcript.start_time:
                logger.warning(f"Skipping transcript ID {t_id} as it was not found or has no start_time.")
                continue

            # Ensure transcript.start_time is timezone-aware (UTC) for correct comparison
            if transcript.start_time.tzinfo is None:
                transcript_start_time_utc = transcript.start_time.replace(tzinfo=timezone.utc)
            else:
                transcript_start_time_utc = transcript.start_time.astimezone(timezone.utc)

            chunks: List[Chunk] = crud.get_chunks_by_transcript_id(db, t_id)
            logger.debug(f"Transcript ID {t_id} (starts {transcript_start_time_utc}) has {len(chunks)} chunks.")

            for chunk in chunks:
                if chunk.start_time is None: # Check if chunk.start_time is None
                    logger.debug(f"Chunk ID {chunk.id} in transcript {t_id} has no start_time, skipping.")
                    continue

                # Calculate chunk's absolute start time
                chunk_absolute_start_time = transcript_start_time_utc + timedelta(seconds=chunk.start_time)

                # Filter:
                # 1. Chunk's absolute date must match target_date.
                # 2. Chunk's absolute time must be within the [timeframe_window_start, timeframe_window_end)
                #    (start inclusive, end exclusive)
                if (chunk_absolute_start_time.date() == target_date and
                    chunk_absolute_start_time >= timeframe_window_start and
                    chunk_absolute_start_time < timeframe_window_end):
                    
                    relevant_chunks_content.append(chunk.content)
                    logger.debug(f"  Added chunk ID {chunk.id} (abs_start: {chunk_absolute_start_time}) to relevant content for timeframe '{timeframe_key}'.")
                else:
                    logger.debug(f"  Skipped chunk ID {chunk.id} (abs_start: {chunk_absolute_start_time}). Does not fit timeframe '{timeframe_key}' ({timeframe_window_start.time()}-{timeframe_window_end.time()}) on {target_date}.")
        
        if not relevant_chunks_content:
            logger.info(f"No chunks found within timeframe '{timeframe_key}' for date {target_date}.")
            return ""

        return "\n\n".join(relevant_chunks_content) # Concatenate with double newline for separation

    except sqlite3.Error as e:
        logger.error(f"Database error while fetching transcript for timeframe {timeframe_key} on {target_date}: {e}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"Unexpected error while fetching transcript for timeframe {timeframe_key} on {target_date}: {e}", exc_info=True)
        return None 