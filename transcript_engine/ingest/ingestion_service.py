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
                # Assuming raw_transcript is now the TranscriptData model from limitless client
                # We need to convert it to TranscriptCreate for crud.save_transcript
                # (Or update crud.save_transcript to accept TranscriptData)
                # For now, let's assume crud.save_transcript needs TranscriptCreate
                if not isinstance(raw_transcript, TranscriptData):
                    logger.error(f"Expected TranscriptData, got {type(raw_transcript)}. Skipping.")
                    skipped_count += 1
                    continue
                
                # Create the Pydantic model for DB insertion
                transcript_to_create = TranscriptCreate(
                    source=raw_transcript.source,
                    source_id=raw_transcript.source_id,
                    title=raw_transcript.title,
                    content=raw_transcript.content, # Content should now be assembled
                    start_time=raw_transcript.start_time,
                    end_time=raw_transcript.end_time,
                    # raw_data field is not in TranscriptCreate, maybe add if needed?
                )

                # Pass the Pydantic model to the CRUD function
                transcript_id = crud.create_transcript(db, transcript_to_create)
                if transcript_id:
                     # Fetch the full transcript object now that it's created
                     transcript_obj = crud.get_transcript_by_id(db, transcript_id)
                     if transcript_obj:
                         new_transcripts_for_processing.append(transcript_obj)
                         saved_count += 1
                     else:
                         # This would be unusual if create_transcript succeeded
                         logger.error(f"Could not retrieve newly created transcript with ID {transcript_id}")
                         skipped_count += 1 # Count as skipped if retrieval failed
                else:
                     # Handle case where create_transcript might fail (e.g., duplicate source_id if IntegrityError wasn't caught/handled upstream)
                     logger.warning(f"Failed to create transcript for source_id {transcript_to_create.source_id} or it already existed.")
                     skipped_count += 1 # Count as skipped

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

                # 1. Chunk text content
                chunk_texts = chunk_text(transcript.content)
                if not chunk_texts:
                    logger.warning(f"No chunks created for transcript ID: {transcript.id}")
                    continue

                logger.debug(f"Generated {len(chunk_texts)} text chunks for transcript ID: {transcript.id}. Generating embeddings...")

                try:
                    # 2. Generate embeddings for the text chunks
                    embeddings_list = embedding_service.embed_documents(chunk_texts)
                    logger.debug(f"Generated {len(embeddings_list)} embeddings.")

                    # 3. Check for mismatch
                    if len(chunk_texts) != len(embeddings_list):
                         logger.error(f"Mismatch between number of text chunks ({len(chunk_texts)}) and embeddings ({len(embeddings_list)}) for transcript {transcript.id}")
                         continue # Skip this transcript

                    # 4. Create structured chunk objects for the vector store
                    # Assuming vector_store.add expects a list of objects (like dicts or Pydantic models)
                    # with 'content', 'embedding', and 'metadata' keys/attributes.
                    structured_chunks_to_add = []
                    for chunk_text_content, embedding_vector in zip(chunk_texts, embeddings_list):
                        # Prepare metadata - minimally the transcript ID
                        metadata = {"transcript_id": transcript.id}
                        # You might add other relevant metadata here if needed later (e.g., start/end offsets if chunker provided them)

                        # Create the structure expected by vector_store.add
                        # Using a dictionary here, adjust if vector_store expects a Pydantic model
                        chunk_data = {
                            "content": chunk_text_content,
                            "embedding": embedding_vector,
                            "metadata": metadata,
                        }
                        structured_chunks_to_add.append(chunk_data)

                    # 5. Add structured chunks to vector store
                    vector_store.add(structured_chunks_to_add) # Use the corrected method name 'add' and pass the list of dicts/models
                    logger.debug(f"Added {len(structured_chunks_to_add)} chunks to vector store for transcript ID: {transcript.id}")
                    total_chunks += len(structured_chunks_to_add)
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