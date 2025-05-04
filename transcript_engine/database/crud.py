"""CRUD (Create, Read, Update, Delete) operations for the database.

This module contains functions for interacting with the database tables.
"""

import sqlite3
import logging
from typing import List, Optional
from datetime import datetime

from transcript_engine.database.schema import ALL_TABLES
from transcript_engine.database.models import Transcript, TranscriptCreate, Chunk, ChunkCreate

logger = logging.getLogger(__name__)

def initialize_database(conn: sqlite3.Connection) -> None:
    """Initializes the database by creating tables if they don't exist.

    Args:
        conn: An active sqlite3 database connection.
    """
    try:
        with conn:
            cursor = conn.cursor()
            for table_sql in ALL_TABLES:
                cursor.execute(table_sql)
            logger.info("Database tables initialized successfully.")
    except sqlite3.Error as e:
        logger.error(f"Error initializing database tables: {e}", exc_info=True)
        raise

# Placeholder CRUD functions - to be implemented later

def create_transcript(conn: sqlite3.Connection, transcript: TranscriptCreate) -> Optional[Transcript]:
    """Creates a new transcript record in the database.

    Args:
        conn: An active sqlite3 database connection.
        transcript: The transcript data to create.

    Returns:
        The created transcript object or None if creation failed.
        
    Raises:
        sqlite3.IntegrityError: If a transcript with the same source_id already exists.
        sqlite3.Error: For other database errors during insertion.
    """
    sql = """INSERT INTO transcripts (source, source_id, title, content)
             VALUES (?, ?, ?, ?)"""
    
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                sql,
                (
                    transcript.source,
                    transcript.source_id,
                    transcript.title,
                    transcript.content,
                ),
            )
            transcript_id = cursor.lastrowid
            logger.info(f"Created transcript with source_id '{transcript.source_id}' and id {transcript_id}")
            
            # Fetch the newly created transcript to include timestamps
            created_transcript_row = cursor.execute(
                "SELECT * FROM transcripts WHERE id = ?", (transcript_id,)
            ).fetchone()
            
            if created_transcript_row:
                return Transcript.model_validate(dict(created_transcript_row)) # Use model_validate for Pydantic v2
            else:
                logger.error(f"Failed to fetch newly created transcript with id {transcript_id}")
                return None
                
    except sqlite3.IntegrityError as e:
        logger.warning(f"Transcript with source_id '{transcript.source_id}' already exists: {e}")
        raise # Re-raise to be handled by the caller
    except sqlite3.Error as e:
        logger.error(f"Error creating transcript with source_id '{transcript.source_id}': {e}", exc_info=True)
        raise

def get_transcript_by_source_id(conn: sqlite3.Connection, source_id: str) -> Optional[Transcript]:
    """Retrieves a transcript by its source ID.

    Args:
        conn: An active sqlite3 database connection.
        source_id: The unique source ID of the transcript.

    Returns:
        The transcript object or None if not found.
        
    Raises:
        sqlite3.Error: For database errors during query.
    """
    sql = "SELECT * FROM transcripts WHERE source_id = ?"
    try:
        with conn:
            cursor = conn.cursor()
            row = cursor.execute(sql, (source_id,)).fetchone()
            if row:
                logger.debug(f"Retrieved transcript with source_id '{source_id}'")
                return Transcript.model_validate(dict(row))
            else:
                logger.debug(f"Transcript with source_id '{source_id}' not found.")
                return None
    except sqlite3.Error as e:
        logger.error(f"Error retrieving transcript with source_id '{source_id}': {e}", exc_info=True)
        raise

def get_latest_transcript_timestamp(conn: sqlite3.Connection) -> Optional[datetime]:
    """Retrieves the creation timestamp of the most recently added transcript.

    Args:
        conn: An active sqlite3 database connection.

    Returns:
        The datetime object of the latest transcript's created_at timestamp, 
        or None if the table is empty.
        
    Raises:
        sqlite3.Error: For database errors during query.
    """
    sql = "SELECT MAX(created_at) FROM transcripts"
    try:
        with conn:
            cursor = conn.cursor()
            result = cursor.execute(sql).fetchone()
            if result and result[0]:
                # SQLite timestamp might be string, attempt to parse
                try:
                    # Assuming format like 'YYYY-MM-DD HH:MM:SS' 
                    # Adjust format if database stores it differently
                    timestamp_str = result[0]
                    # Handle potential timezone info if stored (e.g., appended +00:00)
                    timestamp_str = timestamp_str.split('+')[0].split('.')[0] 
                    latest_time = datetime.fromisoformat(timestamp_str)
                    logger.debug(f"Retrieved latest transcript timestamp: {latest_time}")
                    return latest_time
                except (ValueError, TypeError) as e:
                     logger.error(f"Error parsing timestamp from database '{result[0]}': {e}")
                     # Fallback or re-raise depending on desired strictness
                     return None 
            else:
                logger.info("No transcripts found in the database to get latest timestamp.")
                return None
    except sqlite3.Error as e:
        logger.error(f"Error retrieving latest transcript timestamp: {e}", exc_info=True)
        raise

# Add more CRUD functions for transcripts and chunks as needed 