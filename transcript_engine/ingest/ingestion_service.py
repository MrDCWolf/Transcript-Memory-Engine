"""Service responsible for orchestrating the transcript ingestion pipeline."""

import asyncio
import logging
import time
from typing import AsyncGenerator, Dict, Any, Optional, List
from datetime import datetime, timezone

from transcript_engine.database import crud
from transcript_engine.interfaces.limitless import LimitlessInterface, TranscriptData
from transcript_engine.processing.chunking import chunk_text # Assuming simple chunking for now
from transcript_engine.interfaces.embedding_interface import EmbeddingInterface
from transcript_engine.interfaces.vector_store_interface import VectorStoreInterface
from transcript_engine.database.models import TranscriptCreate, ChunkCreate

logger = logging.getLogger(__name__)

# Global status tracking (replace with a more robust state management if needed)
INGESTION_STATUS: Dict[str, Any] = {
    "status": "idle",  # idle, running, complete, error
    "current_stage": None, # fetch, db_load, process, None
    "completed_stages": [], # List of completed stage names
    "last_run": None, # Timestamp of last run start
    "last_error": None,
    "message": "Waiting to start."
}

# Define stages
STAGES = ["fetch", "db_load", "process"]

async def run_ingestion_pipeline(
    db: Any, # Use actual type hint like sqlite3.Connection if available
    limitless_client: LimitlessInterface, 
    embedding_service: EmbeddingInterface,
    vector_store: VectorStoreInterface,
    start_from_date: Optional[datetime] = None
) -> None: # No longer an AsyncGenerator
    """
    Runs the full transcript ingestion pipeline.

    1. Fetches new transcripts from Limitless since the last run.
    2. Filters out irrelevant transcripts.
    3. Stores new transcripts in the SQLite DB.
    4. Chunks transcripts.
    5. Generates embeddings for chunks.
    6. Stores chunks and embeddings in the vector store.
    Updates the global INGESTION_STATUS dictionary throughout the process.
    """
    run_start_time = datetime.now(timezone.utc)
    logger.info(f"Starting ingestion pipeline run at {run_start_time}...")
    INGESTION_STATUS.update({
        "status": "running",
        "current_stage": "fetch",
        "completed_stages": [],
        "last_run": run_start_time.isoformat(),
        "last_error": None,
        "message": "Starting fetch..."
    })

    try:
        # === Fetch Stage ===
        INGESTION_STATUS.update({"current_stage": "fetch", "message": "Fetching transcripts from Limitless..."})
        logger.info(f"Fetching transcripts starting from: {start_from_date}")
        
        # Consume the async generator properly
        new_transcripts_raw = []
        async for transcript_data in limitless_client.fetch_transcripts(since=start_from_date):
             new_transcripts_raw.append(transcript_data)
        
        logger.info(f"Fetched {len(new_transcripts_raw)} raw transcripts.")
        INGESTION_STATUS["completed_stages"].append("fetch")
        INGESTION_STATUS.update({"message": f"Fetched {len(new_transcripts_raw)} raw transcripts."})

        # === DB Load Stage ===
        INGESTION_STATUS.update({"current_stage": "db_load", "message": "Filtering and saving transcripts to database..."})
        saved_count = 0
        skipped_count = 0
        new_transcripts_for_processing = []
        with db: # Use context manager for transaction
            for raw_transcript in new_transcripts_raw:
                if should_skip_transcript(raw_transcript.get("text", "")):
                    logger.debug(f"Skipping transcript {raw_transcript.get('startTime')} due to content.")
                    skipped_count += 1
                    continue

                transcript = crud.save_transcript(db, raw_transcript)
                if transcript:
                    new_transcripts_for_processing.append(transcript)
                    saved_count += 1
                else:
                    # Should not happen if save_transcript handles errors/duplicates gracefully
                    logger.warning(f"Failed to save transcript {raw_transcript.get('startTime')}") # Or transcript already exists

        logger.info(f"Saved {saved_count} new transcripts to DB. Skipped {skipped_count}.")
        INGESTION_STATUS["completed_stages"].append("db_load")
        INGESTION_STATUS.update({"message": f"Saved {saved_count} new transcripts, skipped {skipped_count}."})

        # === Process Stage (Chunking & Embedding) ===
        INGESTION_STATUS.update({"current_stage": "process", "message": f"Processing {len(new_transcripts_for_processing)} new transcripts..."})
        processed_count = 0
        total_chunks = 0
        if new_transcripts_for_processing:
            logger.info(f"Starting chunking and embedding for {len(new_transcripts_for_processing)} transcripts...")
            for i, transcript in enumerate(new_transcripts_for_processing):
                logger.debug(f"Processing transcript {i+1}/{len(new_transcripts_for_processing)} (ID: {transcript.id})")
                INGESTION_STATUS["message"] = f"Processing transcript {i+1}/{len(new_transcripts_for_processing)}..."

                chunks = chunk_text(transcript.content)
                if not chunks:
                    logger.warning(f"No chunks created for transcript ID: {transcript.id}")
                    continue

                logger.debug(f"Generated {len(chunks)} chunks for transcript ID: {transcript.id}. Generating embeddings...")
                chunk_texts = [chunk for chunk in chunks]

                try:
                    embeddings = await embedding_service.encode(chunk_texts)
                    logger.debug(f"Generated {len(embeddings)} embeddings.")

                    # Add embeddings to chunk objects
                    for chunk, embedding in zip(chunks, embeddings):
                        chunk.embedding = embedding.tolist() # Assuming embedding is numpy array or similar

                    # Add chunks to vector store
                    vector_store.add_chunks(chunks)
                    logger.debug(f"Added {len(chunks)} chunks to vector store for transcript ID: {transcript.id}")
                    total_chunks += len(chunks)
                    processed_count += 1

                except Exception as e:
                    logger.error(f"Error processing transcript ID {transcript.id}: {e}", exc_info=True)
                    # Decide if we should stop the whole process or skip this transcript
                    INGESTION_STATUS.update({
                        "status": "error",
                        "current_stage": "process",
                        "last_error": f"Error processing transcript {transcript.id}: {e}",
                        "message": f"Error processing transcript {transcript.id}."
                    })
                    return # Stop pipeline on error during processing

            logger.info(f"Finished processing {processed_count} transcripts, generating {total_chunks} chunks/embeddings.")
        else:
            logger.info("No new transcripts needed processing.")

        INGESTION_STATUS["completed_stages"].append("process")
        final_message = f"Ingestion complete. Processed {processed_count}/{len(new_transcripts_for_processing)} new transcripts. Added {total_chunks} chunks."
        if saved_count == 0 and len(new_transcripts_for_processing) == 0:
             final_message = "Ingestion complete. No new transcripts found or processed."

        INGESTION_STATUS.update({
            "status": "complete",
            "current_stage": None,
            "message": final_message
        })
        logger.info(final_message)

    except Exception as e:
        logger.error(f"Error during ingestion pipeline stage '{INGESTION_STATUS.get('current_stage')}': {e}", exc_info=True)
        INGESTION_STATUS.update({
            "status": "error",
            "last_error": f"Error in stage '{INGESTION_STATUS.get('current_stage')}': {e}",
            "message": f"Pipeline failed at stage '{INGESTION_STATUS.get('current_stage')}'."
        })

    finally:
        # Ensure status isn't stuck on 'running' if an unexpected exit occurs
        if INGESTION_STATUS["status"] == "running":
             logger.warning("Pipeline function exited unexpectedly while status was 'running'. Setting to error.")
             INGESTION_STATUS.update({
                 "status": "error",
                 "last_error": "Pipeline exited unexpectedly.",
                 "message": "Pipeline exited unexpectedly."
             })

# Helper function needed in CRUD (or adapt existing)
# Add these to transcript_engine/database/crud.py if they don't exist:
# def get_chunks_by_ids(conn: sqlite3.Connection, chunk_ids: List[int]) -> List[Chunk]: ...
# def mark_chunks_embedded(conn: sqlite3.Connection, chunk_ids: List[int]) -> bool: ... 