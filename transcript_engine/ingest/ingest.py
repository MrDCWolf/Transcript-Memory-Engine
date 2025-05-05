"""Module for ingesting transcripts from the Limitless API."""

import logging
import os
import sqlite3
from typing import List, Optional
from datetime import datetime

from transcript_engine.core.config import Settings
from transcript_engine.database.crud import get_db
from transcript_engine.ingest.fetcher import fetch_transcripts
from transcript_engine.database.models import TranscriptCreate

logger = logging.getLogger(__name__)

async def ingest_transcripts(
    settings: Settings,
    # Accept start/end times instead of target_date
    start_time_iso: Optional[str] = None, 
    end_time_iso: Optional[str] = None, 
    timezone: str = "UTC",
) -> int: # Return count of ingested transcripts
    """Ingest transcripts from the Limitless API into the database for a specific time range.

    Args:
        settings: Application settings.
        start_time_iso: Optional start datetime in ISO format (YYYY-MM-DD or YYYY-MM-DD HH:MM:SS).
        end_time_iso: Optional end datetime in ISO format.
        timezone: IANA timezone specifier. Defaults to UTC.
        
    Returns:
        The number of new transcripts successfully fetched and ingested.
    """
    # Log the time range being ingested
    ingest_range_log = f"from {start_time_iso}" if start_time_iso else "latest"
    if end_time_iso:
         ingest_range_log += f" to {end_time_iso}"
    logger.info(f"Starting transcript ingestion for range: {ingest_range_log}...")
    
    api_key = os.getenv("LIMITLESS_API_KEY")
    if not api_key:
        logger.error("Limitless API key is missing in environment variable LIMITLESS_API_KEY.")
        raise ValueError("Limitless API key not configured in environment.")

    transcripts_to_ingest: List[TranscriptCreate] = []
    ingested_count = 0
    
    try:
        # Fetch transcripts from the API
        transcripts_to_ingest = await fetch_transcripts(
            api_key=api_key,
            start_time_iso=start_time_iso,
            end_time_iso=end_time_iso,
            timezone=timezone,
        )

        if not transcripts_to_ingest:
            logger.warning(f"No transcripts found to ingest for range: {ingest_range_log}.")
            return 0

        logger.info(f"Fetched {len(transcripts_to_ingest)} transcripts from the API for range: {ingest_range_log}.")

        # --- Duplicate Checking & Insertion --- 
        existing_source_ids = set()
        try:
            with get_db() as conn_check:
                cursor_check = conn_check.cursor()
                cursor_check.execute("SELECT source_id FROM transcripts WHERE source = ?", ("limitless",))
                existing_source_ids = {row[0] for row in cursor_check.fetchall()}
                logger.debug(f"Found {len(existing_source_ids)} existing Limitless source_ids in DB.")
        except Exception as e:
             logger.error(f"Error checking existing transcripts: {e}", exc_info=True)
             # Continue without duplicate check if this fails

        inserted_transcripts: List[TranscriptCreate] = []
        with get_db() as conn_insert:
            cursor_insert = conn_insert.cursor()
            for transcript in transcripts_to_ingest:
                if transcript.source_id in existing_source_ids:
                     logger.debug(f"Skipping already existing transcript with source_id: {transcript.source_id}")
                     continue
                 
                try:
                     cursor_insert.execute(
                         """
                         INSERT INTO transcripts (source, source_id, title, content, start_time, end_time)
                         VALUES (?, ?, ?, ?, ?, ?)
                         """,
                         (
                             transcript.source,
                             transcript.source_id,
                             transcript.title,
                             transcript.content,
                             transcript.start_time,
                             transcript.end_time,
                         ),
                     )
                     inserted_transcripts.append(transcript)
                     existing_source_ids.add(transcript.source_id)
                except sqlite3.IntegrityError:
                     logger.warning(f"Integrity error (likely duplicate source_id {transcript.source_id}) on insert. Skipping.")
                     existing_source_ids.add(transcript.source_id)
                except Exception as e_insert:
                     logger.error(f"Error inserting transcript {transcript.source_id}: {e_insert}", exc_info=True)
                     
            conn_insert.commit()
            ingested_count = len(inserted_transcripts)
        # ------------------------------------

        logger.info(f"Successfully ingested {ingested_count} new transcripts into the database for range: {ingest_range_log}.")
        return ingested_count

    except Exception as e:
        logger.error(f"Error during transcript ingestion for range {ingest_range_log}: {e}", exc_info=True)
        return 0 