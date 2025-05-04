"""Module for retrieving relevant document chunks based on similarity.
"""

import logging
from typing import List, Dict, Any, Optional

from transcript_engine.interfaces.embedding_interface import EmbeddingInterface
from transcript_engine.interfaces.vector_store_interface import VectorStoreInterface
from transcript_engine.database.models import Chunk

logger = logging.getLogger(__name__)

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

    def retrieve(
        self, 
        query_text: str, 
        k: int = DEFAULT_K, 
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Embeds a query and retrieves the top k similar chunks.

        Args:
            query_text: The user's query string.
            k: The number of chunks to retrieve.
            filter_metadata: Optional metadata to filter the search results.

        Returns:
            A list of dictionaries representing the retrieved documents,
            ordered by similarity. Each dict contains at least 'id' and 'content'.
            Returns an empty list if an error occurs during embedding or querying.
        """
        if not query_text:
            logger.warning("Retrieve called with empty query text.")
            return []
            
        logger.info(f"Retrieving top {k} chunks for query: '{query_text[:100]}...'")
        try:
            # 1. Embed the query
            logger.debug("Generating query embedding...")
            query_embedding = self.embedding_service.embed_query(query_text)
            logger.debug("Query embedding generated.")

            # 2. Query the vector store
            logger.debug("Querying vector store...")
            retrieved_chunks = self.vector_store.query(
                query_embedding=query_embedding,
                k=k,
                filter_metadata=filter_metadata
            )
            logger.info(f"Retrieved {len(retrieved_chunks)} chunks from vector store.")
            return retrieved_chunks

        except Exception as e:
            logger.error(
                f"Error during retrieval for query '{query_text[:100]}...': {e}", 
                exc_info=True
            )
            # Return empty list on error to avoid downstream issues
            return []