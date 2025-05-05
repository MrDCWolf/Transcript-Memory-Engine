import logging
import sqlite3
import time

from transcript_engine.core.dependencies import get_db
from transcript_engine.database import crud
from transcript_engine.database.models import ChunkCreate
from transcript_engine.processing.chunking import chunk_text

# Configure logging
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

# Constants
TRANSCRIPT_BATCH_SIZE = 10 # Process N transcripts at a time
CHUNK_BATCH_SIZE = 100 # Insert M chunks at a time

def main():
    """Main function to find unchunked transcripts and chunk them."""
    logger.info("--- Starting Transcript Chunking Script ---")
    db_conn: sqlite3.Connection | None = None
    processed_count = 0
    total_chunks_created = 0
    
    try:
        db_conn = get_db()
        db_conn.row_factory = sqlite3.Row # Ensure rows can be accessed by column name

        while True:
            logger.info(f"Fetching up to {TRANSCRIPT_BATCH_SIZE} transcripts needing chunking...")
            try:
                transcripts_to_process = crud.get_transcripts_needing_chunking(
                    db_conn, limit=TRANSCRIPT_BATCH_SIZE
                )
            except sqlite3.Error as e:
                logger.error(f"Database error fetching transcripts: {e}", exc_info=True)
                time.sleep(5) # Wait before retrying
                continue

            if not transcripts_to_process:
                logger.info("No more transcripts found needing chunking.")
                break

            logger.info(f"Found {len(transcripts_to_process)} transcripts to process.")
            
            for transcript in transcripts_to_process:
                logger.debug(f"Processing transcript ID: {transcript.id}")
                chunks_to_add: list[ChunkCreate] = []
                try:
                    # Assuming basic text chunking for now
                    # TODO: Incorporate start/end times if available in transcript/chunking logic
                    text_chunks = chunk_text(transcript.content)
                    
                    if not text_chunks:
                         logger.warning(f"Transcript ID {transcript.id} generated no chunks. Skipping.")
                         # Mark as chunked even if empty to avoid reprocessing
                         crud.mark_transcript_chunked(db_conn, transcript.id)
                         processed_count += 1
                         continue

                    for chunk_content in text_chunks:
                        # Placeholder start/end times - needs refinement
                        # Convert datetime to float timestamp for DB insertion
                        start_ts = transcript.start_time.timestamp() if transcript.start_time else None
                        end_ts = transcript.end_time.timestamp() if transcript.end_time else None
                        
                        chunks_to_add.append(
                            ChunkCreate(
                                transcript_id=transcript.id,
                                content=chunk_content,
                                start_time=start_ts, # Use transcript start timestamp
                                end_time=end_ts # Use transcript end timestamp
                            )
                        )
                    
                    # Add chunks in batches (though likely small batches per transcript)
                    if chunks_to_add:
                        crud.add_chunks(db_conn, chunks_to_add)
                        total_chunks_created += len(chunks_to_add)
                        logger.debug(f"Added {len(chunks_to_add)} chunks for transcript {transcript.id}")
                    
                    # Mark the transcript as chunked after successful chunk processing
                    crud.mark_transcript_chunked(db_conn, transcript.id)
                    processed_count += 1
                    logger.info(f"Successfully chunked transcript ID: {transcript.id}")

                except sqlite3.Error as e:
                    logger.error(f"Database error processing transcript {transcript.id}: {e}", exc_info=True)
                    # Decide whether to retry or skip this transcript
                    # For now, we'll log and continue to the next batch
                    break # Break inner loop, try fetching next batch
                except Exception as e:
                    logger.error(
                        f"Unexpected error processing transcript {transcript.id}: {e}", 
                        exc_info=True
                    )
                    # Potentially mark transcript as failed? For now, skip.
                    continue # Continue to next transcript in batch
            
            # Optional: Add a small delay between batches if needed
            # time.sleep(1) 

    except Exception as e:
        logger.critical(f"Unhandled exception in chunking script: {e}", exc_info=True)
    finally:
        if db_conn:
            db_conn.close()
            logger.info("Database connection closed.")
            
    logger.info("--- Transcript Chunking Script Finished ---")
    logger.info(f"Total transcripts processed: {processed_count}")
    logger.info(f"Total chunks created: {total_chunks_created}")


if __name__ == "__main__":
    main() 