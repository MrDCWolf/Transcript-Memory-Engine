"""Interface definition for Text Embedding services.
"""

from typing import Protocol, List, runtime_checkable

# Type alias for embedding vectors
EmbeddingVector = List[float]

@runtime_checkable
class EmbeddingInterface(Protocol):
    """A protocol defining the standard interface for text embedding models.

    This ensures that different embedding backends (SentenceTransformers, OpenAI, etc.)
    can be used interchangeably.
    """

    def embed_documents(self, texts: List[str]) -> List[EmbeddingVector]:
        """Generates embeddings for a list of documents (texts).

        Args:
            texts: A list of strings (documents) to embed.

        Returns:
            A list of embedding vectors, one for each input text.
            
        Raises:
            Exception: For underlying embedding model errors.
        """
        ...

    def embed_query(self, text: str) -> EmbeddingVector:
        """Generates an embedding for a single query text.

        Args:
            text: The query string to embed.

        Returns:
            The embedding vector for the input query.
            
        Raises:
            Exception: For underlying embedding model errors.
        """
        ... 