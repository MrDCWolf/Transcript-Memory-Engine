"""Chunking logic for transcript content."""

import logging
from typing import List

# TODO: Implement more sophisticated chunking (e.g., sentence splitting, semantic chunking)

logger = logging.getLogger(__name__)

DEFAULT_CHUNK_SIZE = 500  # Approximate characters
DEFAULT_CHUNK_OVERLAP = 50  # Approximate characters


def chunk_text(
    text: str,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    chunk_overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> List[str]:
    """Splits text into chunks of a target size with overlap.

    Args:
        text: The text content to chunk.
        chunk_size: The target size for each chunk (in characters).
        chunk_overlap: The overlap between consecutive chunks (in characters).

    Returns:
        A list of text chunks.
    """
    if not text:
        return []

    chunks: List[str] = []
    start = 0
    while start < len(text):
        end = min(start + chunk_size, len(text))
        chunks.append(text[start:end])

        # Move start index for the next chunk, considering overlap
        next_start = start + chunk_size - chunk_overlap
        if next_start <= start:  # Avoid infinite loop if overlap >= size
            next_start = start + 1

        start = next_start
        if start >= len(text):
            break  # Already processed the end

    logger.debug(
        f"Chunked text into {len(chunks)} chunks (size={chunk_size}, overlap={chunk_overlap})."
    )
    return chunks 