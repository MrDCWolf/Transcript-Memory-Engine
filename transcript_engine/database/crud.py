"""CRUD (Create, Read, Update, Delete) operations for the database.

This module contains functions for interacting with the database tables.
"""

import sqlite3
import logging
from typing import List, Optional
from datetime import datetime, timezone
from pathlib import Path
from transcript_engine.core.config import Settings

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

def get_latest_limitless_start_time(conn: sqlite3.Connection) -> Optional[datetime]:
    """Retrieves the latest start_time of an ingested Limitless transcript.

    Args:
        conn: An active sqlite3 database connection.

    Returns:
        The datetime object of the latest transcript's start_time, 
        or None if no Limitless transcripts are found.
        
    Raises:
        sqlite3.Error: For database errors during query.
    """
    sql = "SELECT MAX(start_time) FROM transcripts WHERE source = ?"
    try:
        with conn:
            cursor = conn.cursor()
            result = cursor.execute(sql, ("limitless",)).fetchone()
            if result and result[0]:
                try:
                    # Timestamps are stored as strings, need parsing
                    latest_time = datetime.fromisoformat(result[0])
                    # Ensure timezone awareness (assuming UTC storage)
                    if latest_time.tzinfo is None:
                        latest_time = latest_time.replace(tzinfo=timezone.utc)
                    logger.debug(f"Retrieved latest Limitless transcript start_time: {latest_time}")
                    return latest_time
                except (ValueError, TypeError) as e:
                     logger.error(f"Error parsing latest start_time from database '{result[0]}': {e}")
                     return None
            else:
                logger.info("No existing Limitless transcripts found to get latest start_time.")
                return None
    except sqlite3.Error as e:
        logger.error(f"Error retrieving latest Limitless transcript start_time: {e}", exc_info=True)
        raise

# Add more CRUD functions for transcripts and chunks as needed

def get_transcripts_needing_chunking(conn: sqlite3.Connection, limit: int = 10) -> List[Transcript]:
    """Retrieves transcripts that have not yet been chunked.

    Args:
        conn: An active sqlite3 database connection.
        limit: The maximum number of transcripts to retrieve.

    Returns:
        A list of Transcript objects that need chunking.
        
    Raises:
        sqlite3.Error: For database errors during query.
    """
    sql = "SELECT * FROM transcripts WHERE is_chunked = FALSE ORDER BY created_at ASC LIMIT ?"
    transcripts: List[Transcript] = []
    try:
        with conn:
            cursor = conn.cursor()
            rows = cursor.execute(sql, (limit,)).fetchall()
            for row in rows:
                transcripts.append(Transcript.model_validate(dict(row)))
            logger.debug(f"Retrieved {len(transcripts)} transcripts needing chunking.")
            return transcripts
    except sqlite3.Error as e:
        logger.error(f"Error retrieving transcripts needing chunking: {e}", exc_info=True)
        raise

def add_chunks(conn: sqlite3.Connection, chunks: List[ChunkCreate]) -> bool:
    """Adds multiple chunk records to the database in a single transaction.

    Args:
        conn: An active sqlite3 database connection.
        chunks: A list of ChunkCreate objects to insert.

    Returns:
        True if the insertion was attempted successfully, False otherwise.
        Note: Doesn't guarantee insertion if DB constraints fail silently in executemany.
        
    Raises:
        sqlite3.Error: If any database error occurs during the transaction.
    """
    if not chunks:
        return True # Nothing to add
        
    sql = "INSERT INTO chunks (transcript_id, content, start_time, end_time) VALUES (?, ?, ?, ?)"
    chunk_data = [
        (
            chunk.transcript_id, 
            chunk.content, 
            chunk.start_time, 
            chunk.end_time
        ) 
        for chunk in chunks
    ]
    
    try:
        with conn: # Ensures transactionality
            cursor = conn.cursor()
            cursor.executemany(sql, chunk_data)
            # Avoid cursor.lastrowid after executemany as it can be unreliable/None
            logger.info(f"Executed insert for {len(chunks)} chunks (first transcript ID: {chunks[0].transcript_id}).")
        return True # Indicate successful execution attempt
    except sqlite3.Error as e:
        logger.error(f"Error adding chunks to database: {e}", exc_info=True)
        # The transaction will be rolled back automatically by the context manager
        raise # Re-raise the error
        
def get_chunks_needing_embedding(conn: sqlite3.Connection, limit: int = 100) -> List[Chunk]:
    """Retrieves chunks that have not yet been embedded.

    Args:
        conn: An active sqlite3 database connection.
        limit: The maximum number of chunks to retrieve for batch processing.

    Returns:
        A list of Chunk objects that need embedding.
        
    Raises:
        sqlite3.Error: For database errors during query.
    """
    sql = "SELECT * FROM chunks WHERE is_embedded = FALSE ORDER BY created_at ASC LIMIT ?"
    chunks_to_embed: List[Chunk] = []
    try:
        with conn:
            cursor = conn.cursor()
            rows = cursor.execute(sql, (limit,)).fetchall()
            for row in rows:
                chunks_to_embed.append(Chunk.model_validate(dict(row)))
            logger.debug(f"Retrieved {len(chunks_to_embed)} chunks needing embedding.")
            return chunks_to_embed
    except sqlite3.Error as e:
        logger.error(f"Error retrieving chunks needing embedding: {e}", exc_info=True)
        raise

def mark_transcript_chunked(conn: sqlite3.Connection, transcript_id: int) -> bool:
    """Marks a specific transcript as chunked in the database.

    Args:
        conn: An active sqlite3 database connection.
        transcript_id: The ID of the transcript to mark as chunked.

    Returns:
        True if the update was successful (at least one row affected), False otherwise.
        
    Raises:
        sqlite3.Error: For database errors during update.
    """
    sql = "UPDATE transcripts SET is_chunked = TRUE WHERE id = ?"
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(sql, (transcript_id,))
            updated_rows = cursor.rowcount
            if updated_rows > 0:
                logger.debug(f"Marked transcript {transcript_id} as chunked.")
                return True
            else:
                logger.warning(f"Attempted to mark transcript {transcript_id} as chunked, but no matching row found.")
                return False
    except sqlite3.Error as e:
        logger.error(f"Error marking transcript {transcript_id} as chunked: {e}", exc_info=True)
        raise

def mark_chunks_embedded(conn: sqlite3.Connection, chunk_ids: List[int]) -> int:
    """Marks a list of chunks as embedded in the database.

    Args:
        conn: An active sqlite3 database connection.
        chunk_ids: A list of IDs of the chunks to mark as embedded.

    Returns:
        The number of rows updated.
        
    Raises:
        sqlite3.Error: For database errors during update.
    """
    if not chunk_ids:
        return 0
        
    # Create placeholders for the IN clause
    placeholders = ', '.join('?' * len(chunk_ids))
    sql = f"UPDATE chunks SET is_embedded = TRUE WHERE id IN ({placeholders})"
    
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(sql, chunk_ids)
            updated_count = cursor.rowcount
            logger.debug(f"Marked {updated_count} chunks as embedded (IDs: {chunk_ids}).")
            return updated_count
    except sqlite3.Error as e:
        logger.error(f"Error marking chunks {chunk_ids} as embedded: {e}", exc_info=True)
        raise 

def get_db():
    """Get a database connection.

    Returns:
        sqlite3.Connection: A connection to the SQLite database.
    """
    settings = Settings()
    db_path = Path(settings.database_url.replace("sqlite:///", ""))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path) 