"""Pydantic models representing database objects.

These models are used for data validation and structuring when interacting
with the database CRUD operations.
"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class TranscriptBase(BaseModel):
    """Base model for transcript data.
    
    Used for creating new transcripts.
    """
    source: str
    source_id: str
    title: Optional[str] = None
    content: Optional[str] = None

class TranscriptCreate(TranscriptBase):
    """Model for creating a new transcript in the database.
    
    Inherits common fields from TranscriptBase.
    """
    pass

class Transcript(TranscriptBase):
    """Model representing a transcript retrieved from the database.
    
    Includes database-generated fields like id, created_at, updated_at.
    """
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True # Enable ORM mode for compatibility with database rows

class ChunkBase(BaseModel):
    """Base model for chunk data.
    
    Used for creating new chunks.
    """
    transcript_id: int
    content: str
    start_time: Optional[float] = None
    end_time: Optional[float] = None

class ChunkCreate(ChunkBase):
    """Model for creating a new chunk in the database.
    
    Inherits common fields from ChunkBase.
    """
    pass

class Chunk(ChunkBase):
    """Model representing a chunk retrieved from the database.
    
    Includes database-generated fields like id, created_at, updated_at.
    """
    id: int
    # embedding is not included by default, loaded separately if needed
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True 