"""Interface definition for Vector Store services.
"""

from typing import Protocol, List, Dict, Any, Optional, runtime_checkable

# Import the Chunk model from its definition location
from transcript_engine.database.models import Chunk 

# Type alias for embedding vectors
EmbeddingVector = List[float]

@runtime_checkable
class VectorStoreInterface(Protocol):
    """A protocol defining the standard interface for vector store interactions.

    This ensures that different vector databases (Chroma, FAISS, etc.)
    can be used interchangeably.
    """

    def add(self, chunks: List[Chunk], embeddings: List[EmbeddingVector]) -> None:
        """Adds chunks and their corresponding embeddings to the vector store.

        Args:
            chunks: A list of Chunk objects to add.
            embeddings: A list of embedding vectors corresponding to each chunk.
            
        Raises:
            ValueError: If the number of chunks and embeddings doesn't match.
            Exception: For underlying vector store errors.
        """
        ...

    def query(
        self, 
        query_embedding: EmbeddingVector, 
        k: int = 5, 
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Chunk]:
        """Queries the vector store for chunks similar to the query embedding.

        Args:
            query_embedding: The embedding vector of the query.
            k: The number of nearest neighbors to retrieve (default: 5).
            filter_metadata: Optional dictionary to filter results based on metadata.

        Returns:
            A list of retrieved Chunk objects, ordered by similarity.
            
        Raises:
            Exception: For underlying vector store errors.
        """
        ... 