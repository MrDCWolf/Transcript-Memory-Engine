"""Module for retrieving relevant document chunks based on similarity.
"""

import logging
from typing import List, Dict, Any, Optional
import re # Import regex for simple keyword matching
from datetime import datetime, timedelta, timezone # Import datetime
import sqlite3 # Import sqlite3 for type hinting

from transcript_engine.interfaces.embedding_interface import EmbeddingInterface
from transcript_engine.interfaces.vector_store_interface import VectorStoreInterface
from transcript_engine.database.models import Chunk
from transcript_engine.database import crud # Import crud for transcript ID lookup

logger = logging.getLogger(__name__)

# Simple regex to check for "today" (case-insensitive, word boundary)
TODAY_REGEX = re.compile(r'\btoday\b', re.IGNORECASE)

class SimilarityRetriever:
    """Retrieves relevant chunks using vector similarity search.

    Uses an embedding service to embed the query and a vector store
    to perform the search.
    """

    DEFAULT_K = 5 # Default number of chunks to retrieve

    def __init__(self, embedding_service: EmbeddingInterface, vector_store: VectorStoreInterface):
        """Initializes the SimilarityRetriever.

        Args:
            embedding_service: An instance conforming to EmbeddingInterface.
            vector_store: An instance conforming to VectorStoreInterface.
        """
        self.embedding_service = embedding_service
        self.vector_store = vector_store
        logger.info("SimilarityRetriever initialized.")

    def _get_today_filter(self, db_conn: sqlite3.Connection) -> Optional[Dict[str, Any]]:
        """If possible, generates a ChromaDB metadata filter for today's transcripts.
        
        Args:
            db_conn: An active sqlite3 database connection.
        """
        if not db_conn:
             logger.warning("Database connection not provided to _get_today_filter. Cannot apply filter.")
             return None
             
        try:
            # No longer need with get_db():
            now_utc = datetime.now(timezone.utc)
            start_of_day = datetime(now_utc.year, now_utc.month, now_utc.day, 0, 0, 0, tzinfo=timezone.utc)
            # End of day is start of next day (exclusive)
            end_of_day = start_of_day + timedelta(days=1) 
            
            logger.debug(f"Calculating filter range: {start_of_day.isoformat()} to {end_of_day.isoformat()}")
            
            # Get transcript IDs for today using the provided connection
            transcript_ids = crud.get_transcript_ids_by_date_range(db_conn, start_of_day, end_of_day)
            logger.debug(f"Transcript IDs found for today ({start_of_day.date()}): {transcript_ids}")
            
            if not transcript_ids:
                logger.info("No transcripts found for today's date range. No filter applied.")
                return None
                
            # Build the ChromaDB filter using $in operator
            chroma_filter = {
                "transcript_id": {
                    "$in": transcript_ids
                }
            }
            logger.info(f"Applying filter for {len(transcript_ids)} transcript IDs from today.")
            return chroma_filter
        except Exception as e:
            logger.error(f"Failed to generate 'today' filter: {e}", exc_info=True)
            return None # Proceed without filter if an error occurs

    def retrieve(
        self, 
        query_text: str, 
        k: int = DEFAULT_K, 
        filter_metadata: Optional[Dict[str, Any]] = None,
        db_conn: Optional[sqlite3.Connection] = None
    ) -> List[Dict[str, Any]]:
        """Embeds a query and retrieves the top k similar chunks.

        If the query contains "today" AND a db_conn is provided,
        attempts to apply a metadata filter to only search within 
        transcripts from today.

        Args:
            query_text: The user's query string.
            k: The number of chunks to retrieve.
            filter_metadata: Optional *additional* metadata to filter search results.
                             This will be merged with the 'today' filter if applicable.
            db_conn: Optional database connection needed for date filtering.

        Returns:
            A list of dictionaries representing the retrieved documents,
            ordered by similarity. Each dict contains at least 'id' and 'content'.
            Returns an empty list if an error occurs during embedding or querying.
        """
        if not query_text:
            logger.warning("Retrieve called with empty query text.")
            return []
            
        # --- Time Filtering Logic --- 
        final_filter = filter_metadata or {}
        # Check if query likely refers to today AND if db connection is available
        if TODAY_REGEX.search(query_text):
            if db_conn:
                logger.info("Query contains 'today'. Attempting to apply date filter.")
                today_filter = self._get_today_filter(db_conn) # Pass the connection
                if today_filter:
                    final_filter.update(today_filter)
            else:
                 logger.warning("Query contains 'today' but no DB connection provided to retriever. Cannot apply date filter.")
        # --------------------------
        
        logger.info(f"Retrieving top {k} chunks for query: '{query_text[:100]}...'")
        if final_filter:
            logger.info(f"Using filter: {final_filter}")
            
        try:
            # 1. Embed the query
            logger.debug("Generating query embedding...")
            query_embedding = self.embedding_service.embed_query(query_text)
            logger.debug(f"Generated query embedding (shape: {len(query_embedding)}).")

            # --- Always Apply Date Filter for Chat Context ---
            # We assume calls coming through the main RAG pipeline are for 'today'
            # Remove the check for TODAY_REGEX in query_text
            logger.info("Applying filter for today's transcripts (Chat default).")
            filter_dict = self._get_today_filter(db_conn)
            if filter_dict:
                logger.info(f"Applying filter for {len(filter_dict['transcript_id']['$in'])} transcript IDs from today.")
            else:
                logger.warning("Could not generate filter for today, proceeding without date filtering.")
                filter_dict = None # Ensure it's None if filter generation failed
            # ---------------------------------------------

            # Query the vector store with embedding and filter
            logger.info(f"Retrieving top {k} chunks for query: '{query_text[:50]}...'")
            if filter_dict:
                logger.info(f"Using filter: {filter_dict}")
            
            retrieved_chunk_data = self.vector_store.query(
                query_embedding=query_embedding, 
                k=k, 
                filter_metadata=filter_dict
            )
            logger.info(f"Retrieved {len(retrieved_chunk_data)} chunks from vector store.")
            return retrieved_chunk_data

        except Exception as e:
            logger.error(
                f"Error during retrieval for query '{query_text[:100]}...': {e}", 
                exc_info=True
            )
            # Return empty list on error to avoid downstream issues
            return []