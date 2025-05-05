import logging
import sqlite3
import time
from typing import List

# Import settings directly
from transcript_engine.core.config import Settings, get_settings 

# Import dependencies directly, not the getter functions
# from transcript_engine.core.dependencies import (
#     get_db,
#     get_embedding_service,
#     get_vector_store,
# )
from transcript_engine.core.dependencies import get_db # Keep get_db for connection
from transcript_engine.embeddings.bge_local import BGELocalEmbeddings
from transcript_engine.vector_stores.chroma_store import ChromaStore

from transcript_engine.database import crud
from transcript_engine.database.models import Chunk
# Correct interface imports
from transcript_engine.interfaces.embedding_interface import EmbeddingInterface
from transcript_engine.interfaces.vector_store_interface import VectorStoreInterface

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
CHUNK_BATCH_SIZE = 100 # Process N chunks for embedding at a time

def main():
    """Main function to find unembedded chunks, embed them, and add to vector store."""
    logger.info("--- Starting Chunk Embedding Script ---")
    db_conn: sqlite3.Connection | None = None
    processed_chunk_count = 0
    total_added_to_vs = 0
    
    try:
        logger.info("Initializing services...")
        # Instantiate Settings and services directly for script context
        settings = get_settings() # Load settings
        embed_service: EmbeddingInterface = BGELocalEmbeddings(settings=settings)
        vector_store: VectorStoreInterface = ChromaStore(settings=settings)
        db_conn = get_db()
        logger.info("Services initialized.")

        while True:
            logger.info(f"Fetching up to {CHUNK_BATCH_SIZE} chunks needing embedding...")
            # Fetch chunks needing embedding
            chunks_to_process = crud.get_chunks_needing_embedding(db_conn, limit=CHUNK_BATCH_SIZE)
            
            if not chunks_to_process:
                logger.info("No more chunks found needing embedding.")
                break # Exit the loop if no more chunks

            logger.info(f"Found {len(chunks_to_process)} chunks to embed.")
            batch_chunk_ids = [chunk.id for chunk in chunks_to_process]
            batch_chunk_content = [chunk.content for chunk in chunks_to_process]
            
            start_time = time.monotonic()
            
            # 1. Get Embeddings
            try:
                logger.info("Generating embeddings...")
                embeddings = embed_service.embed_documents(batch_chunk_content)
                logger.info(f"Successfully generated {len(embeddings)} embeddings.")
            except Exception as e:
                # Log embedding error but potentially continue to next batch?
                # Or maybe stop if embedding service fails critically.
                logger.error(f"Error generating embeddings for chunk batch (IDs: {batch_chunk_ids[:5]}...): {e}", exc_info=True)
                # Decide on error handling: break, continue, or retry?
                logger.warning("Skipping current batch due to embedding error.")
                continue # Skip to next batch

            # 2. Add to Vector Store
            try:
                logger.info(f"Adding {len(batch_chunk_ids)} chunks and embeddings to vector store...")
                # Pass chunks and embeddings as required by the interface
                vector_store.add(
                    chunks=chunks_to_process, 
                    embeddings=embeddings
                )
                total_added_to_vs += len(chunks_to_process) # Count successful additions
                logger.info("Successfully added chunks and embeddings to vector store.")

            except Exception as e:
                logger.error(f"Error adding chunk batch to vector store (Chunk IDs: {batch_chunk_ids[:5]}...): {e}", exc_info=True)
                # If adding to vector store fails, we probably shouldn't mark as embedded
                logger.warning("Skipping marking chunks as embedded due to vector store error.")
                continue # Skip marking and go to next batch

            # 3. Mark Chunks as Embedded in DB
            try:
                updated_count = crud.mark_chunks_embedded(db_conn, batch_chunk_ids)
                processed_chunk_count += updated_count
                logger.info(f"Successfully marked {updated_count} chunks as embedded in database.")
            except sqlite3.Error as e:
                 logger.error(f"Database error marking chunks as embedded (IDs: {batch_chunk_ids[:5]}...): {e}. These chunks might be reprocessed later.", exc_info=True)
                 # Continue to next batch, but these chunks might be re-fetched
            
            end_time = time.monotonic()
            logger.info(f"Processed batch of {len(chunks_to_process)} chunks in {end_time - start_time:.2f} seconds.")

    except Exception as e:
        logger.critical(f"Unhandled exception in embedding script: {e}", exc_info=True)
    finally:
        # Close the DB connection obtained via get_db if it was established
        # Note: get_db currently provides a persistent connection; closing might be handled elsewhere (e.g., lifespan)
        # If get_db changes to provide unique connections per call, closing here is crucial.
        # if db_conn:
        #     db_conn.close()
        #     logger.info("Database connection closed.")
        logger.info("--- Chunk Embedding Script Finished ---")
        logger.info(f"Total chunks successfully processed and marked as embedded: {processed_chunk_count}")
        # logger.info(f"Total documents added/updated in vector store: {total_added_to_vs}") # Optional detail

if __name__ == "__main__":
    main() 