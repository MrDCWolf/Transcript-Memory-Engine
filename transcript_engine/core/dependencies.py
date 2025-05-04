"""Dependencies module for Transcript Memory Engine.

This module defines FastAPI dependencies used throughout the application.
"""

from fastapi import Depends
from typing import Generator
import sqlite3
from pathlib import Path
import logging # Import logging

from transcript_engine.core.config import Settings, get_settings
from transcript_engine.database.crud import initialize_database
from transcript_engine.embeddings.bge_local import BGELocalEmbeddings
from transcript_engine.vector_stores.chroma_store import ChromaStore
from transcript_engine.llms.ollama_client import OllamaClient
from transcript_engine.interfaces.embedding_interface import EmbeddingInterface
from transcript_engine.interfaces.vector_store_interface import VectorStoreInterface
from transcript_engine.interfaces.llm_interface import LLMInterface
from transcript_engine.query.retriever import SimilarityRetriever
from transcript_engine.query.rag_service import RAGService

logger = logging.getLogger(__name__) # Get logger instance

# --- Singleton instances for services (cached per application lifecycle) ---
# Use simple global variables for simplicity here. 
# For more complex scenarios, consider FastAPI's lifespan events or a dedicated DI container.
_embedding_service: EmbeddingInterface | None = None
_vector_store: VectorStoreInterface | None = None
_llm_service: LLMInterface | None = None
_retriever: SimilarityRetriever | None = None
_rag_service: RAGService | None = None
# -----------------------------------------------------------------------------

# Flag to ensure initialization happens only once per application lifecycle
_db_initialized = False

def get_db(settings: Settings = Depends(get_settings)) -> Generator[sqlite3.Connection, None, None]:
    """Get a database connection and initialize the database on first call.
    
    Args:
        settings: Application settings
        
    Yields:
        sqlite3.Connection: A database connection
    """
    global _db_initialized
    
    db_path = settings.database_url.split("///")[-1]
    
    # Ensure the data directory exists
    data_dir = Path(db_path).parent
    data_dir.mkdir(parents=True, exist_ok=True)
    
    # Create and yield the database connection
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        
        # Initialize database tables if not already done
        if not _db_initialized:
            initialize_database(conn)
            _db_initialized = True
            
        yield conn

# --- Service Dependencies ---

def get_embedding_service(settings: Settings = Depends(get_settings)) -> EmbeddingInterface:
    """Provides a singleton instance of the Embedding Service.
    """
    global _embedding_service
    if _embedding_service is None:
        logger.info("Creating EmbeddingService instance...")
        _embedding_service = BGELocalEmbeddings(settings)
    return _embedding_service

def get_vector_store(settings: Settings = Depends(get_settings)) -> VectorStoreInterface:
    """Provides a singleton instance of the Vector Store Service.
    """
    global _vector_store
    if _vector_store is None:
        logger.info("Creating VectorStore instance...")
        _vector_store = ChromaStore(settings)
    return _vector_store

def get_llm_service(settings: Settings = Depends(get_settings)) -> LLMInterface:
    """Provides a singleton instance of the LLM Service.
    """
    global _llm_service
    if _llm_service is None:
        logger.info("Creating LLMService instance...")
        _llm_service = OllamaClient(settings)
    return _llm_service

def get_retriever(
    embedding_service: EmbeddingInterface = Depends(get_embedding_service),
    vector_store: VectorStoreInterface = Depends(get_vector_store)
) -> SimilarityRetriever:
    """Provides a singleton instance of the Similarity Retriever.
    """
    global _retriever
    if _retriever is None:
        logger.info("Creating SimilarityRetriever instance...")
        _retriever = SimilarityRetriever(embedding_service=embedding_service, vector_store=vector_store)
    return _retriever

def get_rag_service(
    retriever: SimilarityRetriever = Depends(get_retriever),
    llm: LLMInterface = Depends(get_llm_service)
) -> RAGService:
    """Provides a singleton instance of the RAG Service.
    """
    global _rag_service
    if _rag_service is None:
        logger.info("Creating RAGService instance...")
        _rag_service = RAGService(retriever=retriever, llm=llm)
    return _rag_service
# -------------------------- 