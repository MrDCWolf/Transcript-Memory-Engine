"""API Endpoints for managing transcripts.
"""

import sqlite3
import logging
from fastapi import APIRouter, Depends, HTTPException, status
from typing import Optional

from transcript_engine.database.models import Transcript, TranscriptCreate
from transcript_engine.database import crud
from transcript_engine.core.dependencies import get_db

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/transcripts",
    tags=["Transcripts"], # Tag for OpenAPI documentation
    responses={404: {"description": "Not found"}}, # Default 404 response
)

@router.post(
    "/", 
    response_model=Transcript, 
    status_code=status.HTTP_201_CREATED,
    summary="Create a new transcript",
    description="Creates a new transcript record in the database."
)
async def create_new_transcript(
    transcript: TranscriptCreate,
    conn: sqlite3.Connection = Depends(get_db)
) -> Transcript:
    """Endpoint to create a new transcript.

    Args:
        transcript: The transcript data from the request body.
        conn: Database connection dependency.

    Returns:
        The created transcript object.
        
    Raises:
        HTTPException 409: If a transcript with the same source_id already exists.
        HTTPException 500: For other database errors.
    """
    try:
        created_transcript = crud.create_transcript(conn=conn, transcript=transcript)
        if created_transcript is None:
             # Should ideally not happen if create_transcript raises errors properly
            logger.error(f"create_transcript returned None unexpectedly for source_id: {transcript.source_id}")
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to create transcript."
            )
        return created_transcript
    except sqlite3.IntegrityError:
        logger.warning(f"Attempted to create duplicate transcript with source_id: {transcript.source_id}")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Transcript with source_id '{transcript.source_id}' already exists."
        )
    except sqlite3.Error as e:
        logger.error(f"Database error creating transcript: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while creating transcript."
        )

@router.get(
    "/{source_id}", 
    response_model=Transcript,
    summary="Get a transcript by source ID",
    description="Retrieves a specific transcript using its unique source identifier."
)
async def read_transcript(
    source_id: str, 
    conn: sqlite3.Connection = Depends(get_db)
) -> Transcript:
    """Endpoint to retrieve a transcript by its source ID.

    Args:
        source_id: The source ID of the transcript to retrieve.
        conn: Database connection dependency.

    Returns:
        The requested transcript object.

    Raises:
        HTTPException 404: If the transcript is not found.
        HTTPException 500: For database errors.
    """
    try:
        db_transcript = crud.get_transcript_by_source_id(conn=conn, source_id=source_id)
        if db_transcript is None:
            logger.debug(f"Transcript not found for source_id: {source_id}")
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transcript not found")
        return db_transcript
    except sqlite3.Error as e:
        logger.error(f"Database error retrieving transcript: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database error occurred while retrieving transcript."
        )

# Add endpoints for listing, updating, deleting transcripts later if needed 