"""Dependencies module for Transcript Memory Engine.

This module defines FastAPI dependencies used throughout the application.
"""

from fastapi import Depends, Request
from typing import Generator
import sqlite3
from pathlib import Path
import logging # Import logging
from functools import lru_cache

from fastapi.templating import Jinja2Templates
from markdown_it import MarkdownIt # Import Markdown library

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
from transcript_engine.interfaces.limitless import LimitlessInterface, LimitlessAPIClient

logger = logging.getLogger(__name__) # Get logger instance

# --- Singleton instances for services (cached per application lifecycle) ---
# Use simple global variables for singleton pattern within the module scope.
_embedding_service: EmbeddingInterface | None = None
_vector_store: VectorStoreInterface | None = None
_llm_service: LLMInterface | None = None
_retriever: SimilarityRetriever | None = None
_rag_service: RAGService | None = None 
_limitless_client: LimitlessInterface | None = None # Singleton instance
# ---------------------------------------------------------------------------

# Flag to ensure initialization happens only once per application lifecycle
# _db_initialized = False # Handled by lifespan

# --- Basic Configurations & Templates ---

# Remove LRU cache as it prevents settings updates from being picked up reliably
# The underlying pydantic-settings loader is generally efficient enough.
# @lru_cache()
# def get_cached_settings() -> Settings:
#     return get_settings()

# --- Markdown Filter --- 
def markdown_filter(text):
    """Jinja2 filter to convert Markdown text to HTML."""
    md = MarkdownIt()
    return md.render(text)
# ---------------------

def get_templates() -> Jinja2Templates:
    # Determine the base directory of the project
    base_dir = Path(__file__).resolve().parent.parent.parent
    template_dir = base_dir / "templates"
    if not template_dir.is_dir():
         template_dir = Path("templates") 
    # Register the custom filter
    templates = Jinja2Templates(directory=str(template_dir))
    templates.env.filters["markdown"] = markdown_filter
    return templates


# --- Database Dependency ---

# Keep a single connection instance per application lifecycle might be better
# but for simplicity with Depends, yielding a new connection is common.
# Consider connection pooling for higher load.
# _db_initialized = False # Handled by lifespan
_db_connection = None

def get_db() -> sqlite3.Connection:
    """Provides the singleton database connection instance.
    
    Relies on the FastAPI lifespan event to initialize the connection.
    Raises an exception if the connection hasn't been initialized.
    """
    global _db_connection
    
    # Ensure connection is established (usually by lifespan)
    if _db_connection is None:
        # This should ideally not happen if lifespan ran correctly
        # Maybe force initialization here as a fallback?
        settings = get_settings()
        db_url = settings.database_url
        if not db_url.startswith("sqlite:///"):
            raise ValueError(f"Invalid database_url format: {db_url}")
        db_path_str = db_url[len("sqlite:///"):]
        db_path = Path(db_path_str).resolve()
        logger.warning(f"Database connection was None in get_db. Attempting fallback connection to {db_path}.")
        db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            _db_connection = sqlite3.connect(str(db_path), check_same_thread=False)
            _db_connection.row_factory = sqlite3.Row
            logger.info(f"Fallback DB connection established by get_db.")
        except Exception as e:
            logger.critical(f"Failed to establish fallback DB connection in get_db: {e}", exc_info=True)
            raise RuntimeError(f"Database connection could not be established: {e}")

    # Perform a basic check if the connection seems valid
    try:
        _db_connection.total_changes # Accessing this property checks if connection is usable
    except sqlite3.ProgrammingError as e:
         logger.error(f"Database connection appears closed or invalid in get_db: {e}. Attempting reconnect.")
         _db_connection = None # Force re-connection attempt
         settings = get_settings()
         db_url = settings.database_url
         db_path_str = db_url[len("sqlite:///"):]
         db_path = Path(db_path_str).resolve()
         _db_connection = sqlite3.connect(str(db_path), check_same_thread=False)
         _db_connection.row_factory = sqlite3.Row
         logger.info(f"Re-established DB connection in get_db.")
         if _db_connection is None: # If reconnect failed
             raise RuntimeError("Failed to re-establish database connection.")

    return _db_connection


# --- Service Dependencies (Manual Singleton Pattern with Injected Settings) ---

def get_embedding_service(settings: Settings = Depends(get_settings)) -> EmbeddingInterface:
    """Provides the singleton EmbeddingInterface instance, using injected settings."""
    global _embedding_service
    if _embedding_service is None:
        # Use settings provided by FastAPI's dependency injection
        logger.info(f"Creating BGELocalEmbeddings singleton instance with model: {settings.embedding_model}")
        _embedding_service = BGELocalEmbeddings(settings=settings)
    return _embedding_service

def get_vector_store(settings: Settings = Depends(get_settings)) -> VectorStoreInterface:
    """Provides the singleton VectorStoreInterface instance, using injected settings."""
    global _vector_store
    if _vector_store is None:
        # Use settings provided by FastAPI's dependency injection
        logger.info(f"Creating ChromaStore singleton instance...")
        _vector_store = ChromaStore(settings=settings) 
    return _vector_store

def get_llm_service(settings: Settings = Depends(get_settings)) -> LLMInterface:
    """Provides the singleton LLMInterface instance, using injected settings."""
    global _llm_service
    if _llm_service is None:
        # Use settings provided by FastAPI's dependency injection
        logger.info(f"Creating OllamaClient singleton instance for host: {settings.ollama_base_url}")
        _llm_service = OllamaClient(settings=settings)
    return _llm_service

def get_limitless_client(settings: Settings = Depends(get_settings)) -> LimitlessInterface:
    """Provides the singleton LimitlessInterface instance."""
    global _limitless_client
    if _limitless_client is None:
        logger.info("Creating LimitlessAPIClient singleton instance.")
        _limitless_client = LimitlessAPIClient(
            api_key=settings.limitless_api_key, 
            save_dir=settings.raw_response_dir # Pass save dir from settings
        )
    return _limitless_client


# --- Higher-Level Service Dependencies (Using other dependencies) ---

def get_retriever(
    vector_store: VectorStoreInterface = Depends(get_vector_store),
    embedding_service: EmbeddingInterface = Depends(get_embedding_service),
) -> SimilarityRetriever:
    """Provides the singleton SimilarityRetriever instance."""
    global _retriever
    if _retriever is None:
        logger.info("Creating SimilarityRetriever singleton instance.")
        _retriever = SimilarityRetriever(
            vector_store=vector_store,
            embedding_service=embedding_service
        )
    return _retriever

def get_generator( # Renamed from get_rag_service for clarity as per previous step
    retriever: SimilarityRetriever = Depends(get_retriever),
    llm: LLMInterface = Depends(get_llm_service)
) -> RAGService:
    """Provides the singleton RAGService instance."""
    global _rag_service
    if _rag_service is None:
        logger.info("Creating RAGService singleton instance.")
        _rag_service = RAGService(retriever=retriever, llm=llm)
    return _rag_service

def reset_singletons():
    """Resets service singletons that depend on configurable settings."""
    global _llm_service, _rag_service, _retriever, _embedding_service, _limitless_client # Add limitless
    
    reset_needed = False
    if _llm_service is not None:
        logger.info("Resetting LLM service singleton due to potential settings change.")
        _llm_service = None
        reset_needed = True
        
    # RAG service depends on LLM and Retriever
    if _rag_service is not None:
        logger.info("Resetting RAG service singleton due to potential settings change.")
        _rag_service = None
        reset_needed = True
        
    # Retriever depends on Embeddings and Vector Store (Embeddings might change model)
    # Check embedding service too, although it has its own check
    if _embedding_service is not None: # Reset just in case model name changes via UI eventually
        # logger.info("Resetting Embedding service singleton due to potential settings change.")
        # _embedding_service = None # Maybe not needed if getter handles it
        pass # Getter handles model changes
        
    if _retriever is not None:
        logger.info("Resetting Retriever singleton due to potential settings change.")
        _retriever = None
        reset_needed = True
        
    # Add reset for limitless client if its config (API key?) might change via UI later
    if _limitless_client is not None:
        # For now, assume API key doesn't change via UI, so no reset needed.
        # If it could, uncomment below:
        # logger.info("Resetting Limitless client singleton due to potential settings change.")
        # asyncio.run(_limitless_client.close()) # Close old client connection if needed
        # _limitless_client = None
        # reset_needed = True
        pass 

    if not reset_needed:
        logger.info("reset_singletons called, but no relevant services needed resetting.")

# -------------------------- 