"""Implementation of the EmbeddingInterface using local Sentence Transformers models (e.g., BGE).
"""

import logging
from typing import List
import torch

# Ensure sentence-transformers is installed via poetry
from sentence_transformers import SentenceTransformer

from transcript_engine.interfaces.embedding_interface import EmbeddingInterface, EmbeddingVector
from transcript_engine.core.config import Settings

logger = logging.getLogger(__name__)

class BGELocalEmbeddings(EmbeddingInterface):
    """Embedding client using local Sentence Transformer models (like BAAI/bge-*).

    Implements the EmbeddingInterface protocol.
    Handles loading the model and generating embeddings on the appropriate device.
    """
    def __init__(self, settings: Settings):
        """Initializes the Sentence Transformer embedding client.

        Loads the model specified in the settings.
        Determines the optimal device (MPS, CUDA, or CPU).

        Args:
            settings: The application settings containing the embedding_model name.
        """
        self.model_name = settings.embedding_model
        self.device = self._get_optimal_device()
        logger.info(f"Initializing Sentence Transformer with model: {self.model_name} on device: {self.device}")
        
        try:
            # Load the model onto the chosen device
            # trust_remote_code=True might be needed for some models like newer BGE versions
            # TODO: Consider adding trust_remote_code=True based on model requirements
            self.model = SentenceTransformer(self.model_name, device=self.device)
            logger.info(f"Successfully loaded Sentence Transformer model: {self.model_name}")
        except Exception as e:
            logger.error(f"Failed to load Sentence Transformer model '{self.model_name}': {e}", exc_info=True)
            raise

    def _get_optimal_device(self) -> str:
        """Determines the best available device for computations.
        
        Checks for MPS (Apple Silicon GPU), CUDA (NVIDIA GPU), and defaults to CPU.
        
        Returns:
            A string representing the device ('mps', 'cuda', or 'cpu').
        """
        if torch.backends.mps.is_available():
            logger.info("MPS device (Apple Silicon GPU) available.")
            return 'mps'
        elif torch.cuda.is_available():
            logger.info("CUDA device (NVIDIA GPU) available.")
            return 'cuda'
        else:
            logger.info("No GPU detected. Using CPU for embeddings.")
            return 'cpu'

    def embed_documents(self, texts: List[str]) -> List[EmbeddingVector]:
        """Generates embeddings for a list of documents.

        Args:
            texts: A list of strings (documents) to embed.

        Returns:
            A list of embedding vectors.
            
        Raises:
            Exception: If the embedding model fails.
        """
        logger.debug(f"Generating embeddings for {len(texts)} documents using {self.model_name}.")
        try:
            # The model.encode method handles batching internally
            # Convert result to list of lists of floats for type consistency
            embeddings = self.model.encode(texts, convert_to_tensor=False, device=self.device)
            logger.info(f"Successfully generated embeddings for {len(texts)} documents.")
            # Ensure the output is List[List[float]]
            return [embedding.tolist() for embedding in embeddings]
        except Exception as e:
            logger.error(f"Failed to generate document embeddings with {self.model_name}: {e}", exc_info=True)
            raise

    def embed_query(self, text: str) -> EmbeddingVector:
        """Generates an embedding for a single query text.

        Args:
            text: The query string to embed.

        Returns:
            The embedding vector for the query.
            
        Raises:
            Exception: If the embedding model fails.
        """
        logger.debug(f"Generating embedding for query using {self.model_name}.")
        try:
            embedding = self.model.encode(text, convert_to_tensor=False, device=self.device)
            logger.info("Successfully generated embedding for query.")
            # Ensure the output is List[float]
            return embedding.tolist()
        except Exception as e:
            logger.error(f"Failed to generate query embedding with {self.model_name}: {e}", exc_info=True)
            raise 