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

class TranscriptCreate(BaseModel):
    """Model for creating a new transcript in the database.
    
    Inherits common fields from TranscriptBase.
    """
    source: str = "limitless"  # Default source
    source_id: str = ""  # Needs to be populated
    title: Optional[str] = None
    content: Optional[str] = None
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None

class Transcript(TranscriptBase):
    """Model representing a transcript retrieved from the database.
    
    Includes database-generated fields like id, created_at, updated_at.
    """
    id: int
    is_chunked: bool = False
    start_time: datetime | None = None
    end_time: datetime | None = None
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
    is_embedded: bool = False
    # embedding is not included by default, loaded separately if needed
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

# === Chat Message Model ===

class ChatMessage(BaseModel):
    """Model representing a single message in a chat conversation.
    
    Used for interacting with LLM chat endpoints.
    """
    role: str = Field(..., description="The role of the message sender (e.g., 'user', 'assistant', 'system').")
    content: str = Field(..., description="The content of the message.")

    # Potential future additions for storing history:
    # session_id: str
    # timestamp: datetime
    # id: int 