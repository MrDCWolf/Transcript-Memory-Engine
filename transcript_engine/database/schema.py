"""Database schema definitions for Transcript Memory Engine.

This module defines the SQL statements for creating database tables.
"""

CREATE_TRANSCRIPTS_TABLE = """
CREATE TABLE IF NOT EXISTS transcripts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    source_id TEXT UNIQUE NOT NULL,
    title TEXT,
    content TEXT,
    is_chunked BOOLEAN DEFAULT FALSE NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""

CREATE_CHUNKS_TABLE = """
CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    transcript_id INTEGER NOT NULL,
    content TEXT NOT NULL,
    start_time REAL,
    end_time REAL,
    embedding BLOB DEFAULT NULL, -- Store embedding optionally, track status separately
    is_embedded BOOLEAN DEFAULT FALSE NOT NULL, 
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (transcript_id) REFERENCES transcripts (id)
);
"""

# Add more table creation statements as needed (e.g., for chat history, metadata)

ALL_TABLES = [
    CREATE_TRANSCRIPTS_TABLE,
    CREATE_CHUNKS_TABLE,
] 