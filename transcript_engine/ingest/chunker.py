"""Module for splitting transcript text into manageable chunks.
"""

import logging
from typing import List

from langchain_text_splitters import RecursiveCharacterTextSplitter

# Import Pydantic models
# Assuming Transcript might be passed in (contains ID and content)
# and we need to create ChunkCreate objects (which don't have DB id yet)
from transcript_engine.database.models import Transcript, ChunkCreate 

logger = logging.getLogger(__name__)

# Default chunking parameters (consider making these configurable via Settings)
DEFAULT_CHUNK_SIZE = 1000 # Characters
DEFAULT_CHUNK_OVERLAP = 150 # Characters

def chunk_transcript(
    transcript: Transcript, 
    chunk_size: int = DEFAULT_CHUNK_SIZE, 
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP
) -> List[ChunkCreate]:
    """Splits the content of a transcript into chunks.

    Uses RecursiveCharacterTextSplitter to divide the text based on size and overlap.

    Args:
        transcript: The Transcript object containing the content to be chunked.
        chunk_size: The target size for each chunk (in characters).
        chunk_overlap: The overlap between consecutive chunks (in characters).

    Returns:
        A list of ChunkCreate objects, ready to be inserted into the database.
        Returns an empty list if the transcript content is empty or None.
    """
    if not transcript.content:
        logger.warning(f"Transcript {transcript.id} has no content to chunk.")
        return []

    logger.debug(f"Chunking transcript {transcript.id} (source_id: {transcript.source_id}) with size={chunk_size}, overlap={chunk_overlap}")

    text_splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        length_function=len,
        is_separator_regex=False, # Use default separators like \n\n, \n, space, etc.
    )

    try:
        split_texts = text_splitter.split_text(transcript.content)
        
        created_chunks: List[ChunkCreate] = []
        for i, text_chunk in enumerate(split_texts):
            # Create a ChunkCreate object for each text split
            # We don't have precise start/end times here, just the content
            chunk_data = ChunkCreate(
                transcript_id=transcript.id,
                content=text_chunk,
                # start_time and end_time would require more sophisticated logic 
                # based on original transcript format (e.g., word timings)
                start_time=None, 
                end_time=None,
            )
            created_chunks.append(chunk_data)
            
        logger.info(f"Successfully split transcript {transcript.id} into {len(created_chunks)} chunks.")
        return created_chunks

    except Exception as e:
        logger.error(f"Error chunking transcript {transcript.id}: {e}", exc_info=True)
        # Decide on error handling: raise, return empty list, etc.
        # For now, let's return an empty list to avoid halting potential batch processing
        return [] 