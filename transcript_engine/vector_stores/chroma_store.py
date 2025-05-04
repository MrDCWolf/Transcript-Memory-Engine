"""Implementation of the VectorStoreInterface using ChromaDB.
"""

import logging
import chromadb
from chromadb.errors import IDAlreadyExistsError
from typing import List, Dict, Any, Optional
import os

from transcript_engine.interfaces.vector_store_interface import VectorStoreInterface, EmbeddingVector
from transcript_engine.database.models import Chunk
from transcript_engine.core.config import Settings

logger = logging.getLogger(__name__)

class ChromaStore(VectorStoreInterface):
    """Connects to a persistent ChromaDB instance for vector storage.

    Implements the VectorStoreInterface protocol.
    """

    DEFAULT_COLLECTION_NAME = "transcripts"

    def __init__(self, settings: Settings):
        """Initializes the ChromaDB client and collection.

        Args:
            settings: The application settings containing ChromaDB configuration.
        """
        persist_directory = None # Initialize for error logging
        collection_name_from_settings = None
        try:
            # --- WORKAROUND for potential stale Settings object --- 
            # Try loading directly from environment or use default from config.py definition
            # This bypasses potential issues with the loaded `settings` object being stale
            default_persist_dir = "./data/chroma_db" # Default from config.py
            default_collection_name = "transcripts" # Default from config.py
            
            persist_directory = os.getenv("CHROMA_PERSIST_DIRECTORY", default_persist_dir)
            self.collection_name = os.getenv("CHROMA_COLLECTION_NAME", default_collection_name)
            logger.info(f"DEBUG: Chroma path from env/default: {persist_directory}")
            logger.info(f"DEBUG: Chroma collection from env/default: {self.collection_name}")
            # ----------------------------------------------------
            
            # Keep the original attempt as a fallback/for comparison if needed, but it might fail
            # persist_directory = settings.chroma_persist_directory
            # self.collection_name = settings.chroma_collection_name
            
            self.client = chromadb.PersistentClient(path=persist_directory)
            self.collection = self.client.get_or_create_collection(self.collection_name)
            logger.info(
                f"ChromaDB client initialized. Path: '{persist_directory}'. "
                f"Collection: '{self.collection_name}'."
            )
        except AttributeError as e:
            # This might still occur if the original lines are uncommented and fail
            logger.error(f"Configuration error: Missing expected setting in Settings object: {e}", exc_info=True)
            raise
        except Exception as e:
            # Log the path if it was successfully retrieved before the error
            path_info = f"at path '{persist_directory}'" if persist_directory else "(path could not be determined)"
            logger.error(f"Failed to initialize ChromaDB client {path_info}: {e}", exc_info=True)
            raise

    def add(self, chunks: List[Chunk], embeddings: List[EmbeddingVector]) -> None:
        """Adds chunks and their embeddings to the Chroma collection.

        Uses chunk.id as the document ID in Chroma.
        Stores chunk content and relevant metadata.

        Args:
            chunks: A list of Chunk objects.
            embeddings: A list of corresponding embedding vectors.
            
        Raises:
            ValueError: If len(chunks) != len(embeddings).
            Exception: For ChromaDB errors during addition.
        """
        if len(chunks) != len(embeddings):
            raise ValueError("Number of chunks and embeddings must be equal.")
        
        if not chunks: # Nothing to add
            return

        ids = []
        docs = []
        metadatas = []

        for chunk in chunks:
            # Ensure chunk.id is a string for ChromaDB
            chunk_id_str = str(chunk.id)
            ids.append(chunk_id_str)
            docs.append(chunk.content)
            # Store relevant metadata
            metadata = {
                "transcript_id": chunk.transcript_id,
                "start_time": chunk.start_time,
                "end_time": chunk.end_time,
                # Add other relevant metadata from Chunk model if needed
            }
            # Filter out None values from metadata, as Chroma expects serializable types
            metadatas.append({k: v for k, v in metadata.items() if v is not None})

        try:
            logger.debug(f"Adding {len(ids)} chunks to Chroma collection '{self.collection_name}'.")
            # Use upsert to handle potential ID conflicts gracefully if needed, 
            # though ideally IDs should be unique.
            # Using add and catching IDAlreadyExistsError for demonstration as per plan suggestion
            self.collection.add(
                ids=ids,
                embeddings=embeddings,
                documents=docs,
                metadatas=metadatas
            )
            logger.info(f"Successfully added {len(ids)} chunks to Chroma.")
        except IDAlreadyExistsError:
            logger.warning(f"Attempted to add chunks with existing IDs: {ids}. Consider using upsert or checking ID generation.")
            # Depending on desired behavior, you might want to log which specific IDs failed
            # or implement selective upsert logic here.
            pass # Or re-raise if adding duplicates is a critical error
        except Exception as e:
            logger.error(f"Failed to add documents to Chroma: {e}", exc_info=True)
            raise

    def query(
        self, 
        query_embedding: EmbeddingVector, 
        k: int = 5, 
        filter_metadata: Optional[Dict[str, Any]] = None
    ) -> List[Dict[str, Any]]:
        """Queries the Chroma collection for similar chunks.

        Args:
            query_embedding: The embedding vector of the query.
            k: The number of nearest neighbors to retrieve.
            filter_metadata: Optional dictionary for metadata filtering (using Chroma's 'where' clause).

        Returns:
            A list of dictionaries containing the retrieved document 'id' (str),
            'content' (str), and metadata.
            
        Raises:
            Exception: For ChromaDB errors during query.
        """
        try:
            logger.debug(f"Querying Chroma collection '{self.collection_name}' with k={k}.")
            results = self.collection.query(
                query_embeddings=[query_embedding],
                n_results=k,
                where=filter_metadata, # Pass filter directly to Chroma's where clause
                include=['metadatas', 'documents'] # Ensure we get needed data
            )

            retrieved_docs: List[Dict[str, Any]] = []
            if results and results.get('ids') and len(results['ids'][0]) > 0:
                result_ids = results['ids'][0]
                result_metadatas = results.get('metadatas', [[]])[0]
                result_documents = results.get('documents', [[]])[0]
                
                logger.debug(f"Retrieved {len(result_ids)} results from Chroma.")

                for i, chunk_id_str in enumerate(result_ids):
                    metadata = result_metadatas[i] if i < len(result_metadatas) else {}
                    content = result_documents[i] if i < len(result_documents) else ""
                    
                    # Create a dictionary with the retrieved data
                    retrieved_doc = {
                        "id": chunk_id_str, # Keep as string ID from Chroma
                        "content": content,
                        "metadata": metadata # Include the retrieved metadata
                    }
                    retrieved_docs.append(retrieved_doc)

            else:
                 logger.debug("No results found in Chroma for the query.")
                 
            return retrieved_docs
        
        except Exception as e:
            logger.error(f"Failed to query Chroma collection: {e}", exc_info=True)
            # Return empty list on error to prevent downstream failures
            return [] # Return empty list instead of raising 