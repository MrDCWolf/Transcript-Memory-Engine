"""Script to process stored transcripts: chunking and embedding.
"""

import logging
import sqlite3
import sys
import os
from typing import List

# Ensure the main package is in the Python path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from transcript_engine.core.config import get_settings
from transcript_engine.database import crud
from transcript_engine.ingest.chunker import chunk_transcript
from transcript_engine.embeddings.bge_local import BGELocalEmbeddings
from transcript_engine.vector_stores.chroma_store import ChromaStore
from transcript_engine.database.models import Transcript, Chunk
from transcript_engine.interfaces.embedding_interface import EmbeddingInterface
from transcript_engine.interfaces.vector_store_interface import VectorStoreInterface

# --- Logging Setup --- (Same as ingest_transcripts.py for consistency)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger(__name__)
# --- End Logging Setup ---

# --- Configuration --- (Consider moving defaults to Settings)
CHUNK_BATCH_SIZE = 10  # Process N transcripts for chunking at a time
EMBED_BATCH_SIZE = 100 # Process N chunks for embedding at a time
# -------------------

def main():
    """Main function to run the transcript processing pipeline.
    """
    logger.info("Starting transcript processing pipeline (Chunking & Embedding)...")
    settings = get_settings()
    
    conn = None
    try:
        # --- Database Connection ---
        db_path_relative = settings.database_url.split("///")[-1]
        db_path_absolute = os.path.join(project_root, db_path_relative)
        os.makedirs(os.path.dirname(db_path_absolute), exist_ok=True)
        conn = sqlite3.connect(db_path_absolute)
        conn.row_factory = sqlite3.Row
        logger.info(f"Connected to database: {db_path_absolute}")
        # -------------------------
        
        # --- Initialize Services ---
        embedding_service: EmbeddingInterface = BGELocalEmbeddings(settings)
        vector_store: VectorStoreInterface = ChromaStore(settings)
        # -------------------------
        
        # === Chunking Step ===
        logger.info("--- Starting Chunking Step ---")
        processed_transcript_count = 0
        while True:
            logger.info(f"Fetching up to {CHUNK_BATCH_SIZE} transcripts needing chunking...")
            transcripts_to_chunk: List[Transcript] = crud.get_transcripts_needing_chunking(
                conn, limit=CHUNK_BATCH_SIZE
            )
            
            if not transcripts_to_chunk:
                logger.info("No more transcripts found needing chunking.")
                break # Exit chunking loop
            
            logger.info(f"Processing {len(transcripts_to_chunk)} transcripts for chunking.")
            for transcript in transcripts_to_chunk:
                try:
                    logger.debug(f"Chunking transcript ID: {transcript.id}")
                    # TODO: Pass chunk size/overlap from settings if configurable
                    chunks_to_create = chunk_transcript(transcript)
                    
                    if chunks_to_create:
                        logger.debug(f"Adding {len(chunks_to_create)} chunks for transcript ID: {transcript.id}")
                        crud.add_chunks(conn, chunks_to_create)
                    else:
                        logger.warning(f"No chunks created for transcript ID: {transcript.id}. Marking as chunked anyway.")
                        
                    # Mark transcript as chunked even if no chunks were made (e.g., empty content)
                    crud.mark_transcript_chunked(conn, transcript.id)
                    processed_transcript_count += 1
                    
                except Exception as e:
                    logger.error(
                        f"Error processing transcript ID {transcript.id} during chunking step: {e}", 
                        exc_info=True
                    )
                    # Optionally: Add logic to mark transcript as failed_chunking
                    continue # Move to next transcript in batch
            
        logger.info(f"--- Finished Chunking Step. Processed {processed_transcript_count} transcripts. ---")
        
        # === Embedding Step ===
        logger.info("--- Starting Embedding Step ---")
        processed_chunk_count = 0
        while True:
            logger.info(f"Fetching up to {EMBED_BATCH_SIZE} chunks needing embedding...")
            chunks_to_embed: List[Chunk] = crud.get_chunks_needing_embedding(
                conn, limit=EMBED_BATCH_SIZE
            )
            
            if not chunks_to_embed:
                logger.info("No more chunks found needing embedding.")
                break # Exit embedding loop
                
            logger.info(f"Processing {len(chunks_to_embed)} chunks for embedding.")
            chunk_texts = [chunk.content for chunk in chunks_to_embed]
            chunk_ids = [chunk.id for chunk in chunks_to_embed]
            
            try:
                # Generate embeddings
                logger.debug(f"Generating embeddings for {len(chunk_texts)} chunk texts...")
                embeddings = embedding_service.embed_documents(chunk_texts)
                logger.debug(f"Embeddings generated. Shape: ({len(embeddings)}, {len(embeddings[0]) if embeddings else 0})")
                
                # Add to vector store
                logger.debug(f"Adding {len(chunks_to_embed)} chunks with embeddings to vector store...")
                vector_store.add(chunks=chunks_to_embed, embeddings=embeddings)
                logger.debug(f"Chunks added to vector store.")
                
                # Mark chunks as embedded in DB
                logger.debug(f"Marking {len(chunk_ids)} chunks as embedded in database...")
                updated_count = crud.mark_chunks_embedded(conn, chunk_ids)
                logger.debug(f"Marked {updated_count} chunks as embedded.")
                
                processed_chunk_count += len(chunks_to_embed)
            
            except Exception as e:
                logger.error(
                    f"Error processing batch of chunks (IDs starting {chunk_ids[0]}...) during embedding step: {e}", 
                    exc_info=True
                )
                # Depending on severity, might break or continue with next batch
                # For now, we log and break the loop to avoid potential cascading failures
                logger.critical("Halting embedding step due to error.")
                break 
                
        logger.info(f"--- Finished Embedding Step. Processed {processed_chunk_count} chunks. ---")
        logger.info("Transcript processing pipeline finished.")

    except Exception as e:
        logger.critical(f"A critical error occurred during the processing pipeline: {e}", exc_info=True)
    finally:
        if conn:
            conn.close()
            logger.info("Database connection closed.")

if __name__ == "__main__":
    main() 