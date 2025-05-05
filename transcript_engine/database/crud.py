"""CRUD (Create, Read, Update, Delete) operations for the database.

This module contains functions for interacting with the database tables.
"""

import sqlite3
import logging
from typing import List, Optional
from datetime import datetime, timezone, date
from pathlib import Path
from transcript_engine.core.config import Settings

from transcript_engine.database.schema import ALL_TABLES
from transcript_engine.database.models import Transcript, TranscriptCreate, Chunk, ChunkCreate, ChatMessage

logger = logging.getLogger(__name__)

def initialize_database(db_path: str | Path) -> None:
    """Initializes the database by creating tables if they don't exist.

    Args:
        db_path: The path to the SQLite database file.
    """
    # Ensure parent directory exists
    db_path = Path(db_path)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    
    try:
        # Connect, setup, disconnect
        conn = sqlite3.connect(str(db_path))
        try:
            with conn:
                cursor = conn.cursor()
                for table_sql in ALL_TABLES:
                    cursor.execute(table_sql)
                logger.info(f"Database tables initialized successfully at {db_path}.")
        finally:
            conn.close()
    except sqlite3.Error as e:
        logger.error(f"Error initializing database tables at {db_path}: {e}", exc_info=True)
        raise

# Placeholder CRUD functions - to be implemented later

def create_transcript(conn: sqlite3.Connection, transcript: TranscriptCreate) -> Optional[int]:
    """Creates a new transcript record in the database.

    Args:
        conn: An active sqlite3 database connection.
        transcript: The transcript data to create.

    Returns:
        The ID of the created transcript record, or None if creation failed before commit.
        
    Raises:
        sqlite3.IntegrityError: If a transcript with the same source_id already exists.
        sqlite3.Error: For other database errors during insertion.
    """
    sql = """INSERT INTO transcripts (source, source_id, title, content, start_time, end_time)
             VALUES (?, ?, ?, ?, ?, ?)"""
    
    try:
        # Convert datetime objects to ISO 8601 string format for SQLite
        # Store as TEXT - recommended for SQLite date/time
        start_time_iso = transcript.start_time.isoformat() if transcript.start_time else None
        end_time_iso = transcript.end_time.isoformat() if transcript.end_time else None

        with conn:
            cursor = conn.cursor()
            cursor.execute(
                sql,
                (
                    transcript.source,
                    transcript.source_id,
                    transcript.title,
                    transcript.content,
                    start_time_iso, # Pass start_time
                    end_time_iso    # Pass end_time
                ),
            )
            transcript_id = cursor.lastrowid
            if transcript_id is not None:
                logger.info(f"Created transcript with source_id '{transcript.source_id}' and id {transcript_id}")
                return transcript_id
            else:
                # This case should be rare with sqlite unless an error occurred before commit
                logger.error(f"Failed to get lastrowid after inserting transcript with source_id '{transcript.source_id}'")
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

def add_chat_message(conn: sqlite3.Connection, session_id: str, message: ChatMessage) -> Optional[int]:
    """Adds a chat message to the database.

    Args:
        conn: An active sqlite3 database connection.
        session_id: The unique identifier for the chat session.
        message: The ChatMessage object containing role and content.

    Returns:
        The ID of the inserted chat message, or None if insertion failed.
    
    Raises:
        sqlite3.Error: For database errors during insertion.
    """
    sql = """INSERT INTO chat_messages (session_id, role, content)
             VALUES (?, ?, ?)"""
    
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(
                sql,
                (
                    session_id,
                    message.role,
                    message.content,
                ),
            )
            message_id = cursor.lastrowid
            if message_id is not None:
                logger.debug(f"Added chat message ID {message_id} for session {session_id}")
                return message_id
            else:
                logger.error(f"Failed to get lastrowid after inserting chat message for session {session_id}")
                return None
    except sqlite3.Error as e:
        logger.error(f"Error adding chat message for session {session_id}: {e}", exc_info=True)
        raise

def get_chat_history(conn: sqlite3.Connection, session_id: str, limit: int = 50) -> List[ChatMessage]:
    """Retrieves the chat history for a given session ID.

    Args:
        conn: An active sqlite3 database connection.
        session_id: The unique identifier for the chat session.
        limit: The maximum number of messages to retrieve (most recent first).

    Returns:
        A list of ChatMessage objects ordered by timestamp ascending.
    
    Raises:
        sqlite3.Error: For database errors during query.
    """
    # Retrieve messages ordered by timestamp to get the most recent, then reverse in Python for correct order
    sql = "SELECT role, content FROM chat_messages WHERE session_id = ? ORDER BY timestamp DESC LIMIT ?"
    messages: List[ChatMessage] = []
    try:
        with conn:
            cursor = conn.cursor()
            rows = cursor.execute(sql, (session_id, limit)).fetchall()
            for row in reversed(rows): # Reverse here to get chronological order
                # Assume row_factory is working or adapt if needed
                messages.append(ChatMessage(role=row['role'], content=row['content'])) 
            logger.debug(f"Retrieved {len(messages)} messages for session {session_id}")
            return messages
    except sqlite3.Error as e:
        logger.error(f"Error retrieving chat history for session {session_id}: {e}", exc_info=True)
        return [] # Return empty list on error

def get_distinct_transcript_dates(conn: sqlite3.Connection) -> List[date]:
    """Fetches the distinct dates for which transcripts exist.

    Assumes start_time is stored as an ISO 8601 string.

    Args:
        conn: An active sqlite3 database connection.

    Returns:
        A sorted list of unique dates (YYYY-MM-DD) found in the transcripts table.
        Returns an empty list if no transcripts are found or an error occurs.
    
    Raises:
        sqlite3.Error: For database errors during querying.
    """
    # Use SUBSTR or DATE() function on the ISO string column
    sql = """SELECT DISTINCT SUBSTR(start_time, 1, 10) 
             FROM transcripts 
             WHERE start_time IS NOT NULL AND LENGTH(start_time) >= 10
             ORDER BY SUBSTR(start_time, 1, 10)"""
    dates: List[date] = []
    try:
        with conn:
            cursor = conn.cursor()
            cursor.execute(sql)
            rows = cursor.fetchall()
            for row in rows:
                if row[0]: # Ensure the date string is not null/empty
                    try:
                        # The result of SUBSTR is 'YYYY-MM-DD'
                        dates.append(date.fromisoformat(row[0]))
                    except ValueError:
                        logger.warning(f"Could not parse date string '{row[0]}' from database.")
            logger.info(f"Found {len(dates)} distinct transcript dates.")
    except sqlite3.Error as e:
        logger.error(f"Error fetching distinct transcript dates: {e}", exc_info=True)
        # Optionally re-raise, but returning empty list might be safer for the caller

    return dates

def get_db():
    """Get a database connection.

    Returns:
        sqlite3.Connection: A connection to the SQLite database.
    """
    settings = Settings()
    db_path = Path(settings.database_url.replace("sqlite:///", ""))
    db_path.parent.mkdir(parents=True, exist_ok=True)
    return sqlite3.connect(db_path)

def add_transcripts_batch(conn: sqlite3.Connection, transcripts: List[TranscriptCreate]) -> int:
    """Adds multiple transcript records to the database in a single transaction.

    Args:
        conn: An active sqlite3 database connection.
        transcripts: A list of TranscriptCreate objects to insert.

    Returns:
        The number of transcripts successfully prepared for insertion.
        Note: Due to sqlite3 limitations, `executemany` might not report 
              per-row errors (like IntegrityError) without extra handling.
        
    Raises:
        sqlite3.Error: If a database error occurs during the transaction.
    """
    if not transcripts:
        return 0

    sql = """INSERT INTO transcripts (source, source_id, title, content, start_time, end_time)
             VALUES (?, ?, ?, ?, ?, ?)"""
    
    transcript_data = []
    for t in transcripts:
        start_time_iso = t.start_time.isoformat() if t.start_time else None
        end_time_iso = t.end_time.isoformat() if t.end_time else None
        transcript_data.append(
            (
                t.source,
                t.source_id,
                t.title,
                t.content,
                start_time_iso,
                end_time_iso
            )
        )

    try:
        with conn: # Ensures transactionality
            cursor = conn.cursor()
            # Using INSERT OR IGNORE to gracefully handle duplicates within the batch
            # Change to INSERT if strict error checking on duplicates is needed
            cursor.execute("PRAGMA query_only = OFF") # Ensure INSERT is allowed
            insert_sql = """INSERT OR IGNORE INTO transcripts 
                          (source, source_id, title, content, start_time, end_time)
                          VALUES (?, ?, ?, ?, ?, ?)"""
            cursor.executemany(insert_sql, transcript_data)
            inserted_count = cursor.rowcount # rowcount after executemany might be -1 or actual count
            if inserted_count == -1:
                 logger.warning(f"Executed INSERT OR IGNORE for {len(transcript_data)} transcripts batch. Rowcount unreliable (-1).")
                 # Assume all were attempted; duplicates ignored silently
                 return len(transcript_data)
            else:
                 logger.info(f"Executed INSERT OR IGNORE for {len(transcript_data)} transcripts batch. Rows affected: {inserted_count}. (This counts actual insertions, ignoring duplicates).")
                 return inserted_count # Return actual number inserted if available
                 
    except sqlite3.Error as e:
        logger.error(f"Error adding transcript batch to database: {e}", exc_info=True)
        raise # Re-raise the error 