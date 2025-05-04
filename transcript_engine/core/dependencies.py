"""Dependencies module for Transcript Memory Engine.

This module defines FastAPI dependencies used throughout the application.
"""

from fastapi import Depends
from typing import Generator
import sqlite3
from pathlib import Path

from transcript_engine.core.config import Settings, get_settings
from transcript_engine.database.crud import initialize_database

# Flag to ensure initialization happens only once per application lifecycle
_db_initialized = False

def get_db(settings: Settings = Depends(get_settings)) -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection and initialize the database on first call.
    
    Args:
        settings: Application settings
        
    Yields:
        sqlite3.Connection: A database connection
    """
    global _db_initialized
    
    db_path = settings.database_url.split("///")[-1]
    
    # Ensure the data directory exists
    data_dir = Path(db_path).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Create and yield the database connection
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        
        # Initialize database tables if not already done
        if not _db_initialized:
            initialize_database(conn)
            _db_initialized = True
            
        yield conn 