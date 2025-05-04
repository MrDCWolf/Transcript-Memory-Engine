"""Stub implementation of the EmbeddingInterface for testing purposes.
"""

import logging
from typing import List

from transcript_engine.interfaces.embedding_interface import EmbeddingInterface, EmbeddingVector

logger = logging.getLogger(__name__)

class StubEmbedding(EmbeddingInterface):
    """A stub embedding client that returns zero vectors.

    Useful for testing integration without loading a real model.
    Implements the EmbeddingInterface protocol.
    """
    def __init__(self, dimension: int = 384):
        """Initializes the stub embedding client.

        Args:
            dimension: The dimensionality of the zero vectors to return.
        """
        self.dimension = dimension
        logger.info(f"StubEmbedding initialized with dimension {self.dimension}")

    def embed_documents(self, texts: List[str]) -> List[EmbeddingVector]:
        """Returns a list of zero vectors, one for each input text.

        Args:
            texts: A list of strings (documents).

        Returns:
            A list of zero vectors of the configured dimension.
        """
        logger.debug(f"StubEmbedding generating {len(texts)} zero vectors for documents.")
        return [[0.0] * self.dimension for _ in texts]

    def embed_query(self, text: str) -> EmbeddingVector:
        """Returns a single zero vector for the input query text.

        Args:
            text: The query string.

        Returns:
            A zero vector of the configured dimension.
        """
        logger.debug("StubEmbedding generating zero vector for query.")
        return [0.0] * self.dimension 