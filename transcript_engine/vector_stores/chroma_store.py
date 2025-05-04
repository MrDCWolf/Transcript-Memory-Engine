"""Implementation of the VectorStoreInterface using ChromaDB.
"""

import logging
import chromadb
from chromadb.errors import IDAlreadyExistsError
from typing import List, Dict, Any, Optional

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
        try:
            self.client = chromadb.PersistentClient(path=settings.vector_store_path)
            # Use collection name from settings or a default
            # TODO: Add collection name to Settings if needed
            self.collection_name = getattr(settings, 'chroma_collection', self.DEFAULT_COLLECTION_NAME)
            self.collection = self.client.get_or_create_collection(self.collection_name)
            logger.info(
                f"ChromaDB client initialized. Path: '{settings.vector_store_path}'. "
                f"Collection: '{self.collection_name}'."
            )
        except Exception as e:
            logger.error(f"Failed to initialize ChromaDB client at path '{settings.vector_store_path}': {e}", exc_info=True)
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
    ) -> List[Chunk]:
        """Queries the Chroma collection for similar chunks.

        Args:
            query_embedding: The embedding vector of the query.
            k: The number of nearest neighbors to retrieve.
            filter_metadata: Optional dictionary for metadata filtering (using Chroma's 'where' clause).

        Returns:
            A list of retrieved Chunk objects, reconstructed from Chroma results.
            
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

            retrieved_chunks: List[Chunk] = []
            if results and results.get('ids') and len(results['ids'][0]) > 0:
                result_ids = results['ids'][0]
                result_metadatas = results.get('metadatas', [[]])[0]
                result_documents = results.get('documents', [[]])[0]
                
                logger.debug(f"Retrieved {len(result_ids)} results from Chroma.")

                for i, chunk_id_str in enumerate(result_ids):
                    metadata = result_metadatas[i] if i < len(result_metadatas) else {}
                    content = result_documents[i] if i < len(result_documents) else ""
                    
                    # Reconstruct the Chunk object. 
                    # Note: We don't have created_at/updated_at from Chroma.
                    # These would need to be fetched from the primary DB (SQLite) 
                    # if needed for the specific use case after retrieval.
                    try:
                        retrieved_chunk = Chunk(
                            id=int(chunk_id_str), # Convert back to int
                            content=content,
                            transcript_id=metadata.get("transcript_id"),
                            start_time=metadata.get("start_time"),
                            end_time=metadata.get("end_time"),
                            # Set dummy values for fields not stored in Chroma
                            created_at=None, # Not stored in Chroma
                            updated_at=None  # Not stored in Chroma
                        )
                        retrieved_chunks.append(retrieved_chunk)
                    except (ValueError, TypeError) as conversion_error:
                         logger.warning(f"Could not convert Chroma result (ID: {chunk_id_str}) back to Chunk model: {conversion_error}")
                    except Exception as pydantic_error:
                         logger.warning(f"Pydantic validation error for Chroma result (ID: {chunk_id_str}): {pydantic_error}")

            else:
                 logger.debug("No results found in Chroma for the query.")
                 
            return retrieved_chunks
        
        except Exception as e:
            logger.error(f"Failed to query Chroma collection: {e}", exc_info=True)
            raise 