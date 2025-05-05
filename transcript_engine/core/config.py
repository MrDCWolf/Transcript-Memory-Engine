"""Configuration module for Transcript Memory Engine.

This module handles all application configuration using pydantic-settings.
"""

import logging
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pydantic import Field

# Explicitly load .env file BEFORE BaseSettings reads environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# --- In-memory storage for UI-set overrides ---
_ui_set_ollama_url: str | None = None
_ui_set_default_model: str | None = None
# --------------------------------------------

class Settings(BaseSettings):
    """Application settings class.
    
    This class defines all configuration settings for the application.
    Settings are loaded from environment variables with appropriate defaults.
    """
    
    # Application settings
    environment: str = "development"
    debug: bool = False
    
    # Database settings
    database_url: str = Field(default="sqlite:///./data/transcript_engine.db", description="Database connection string.")
    
    # Vector store settings
    vector_store_path: str = Field(default="./data/chroma_db", description="Path to the ChromaDB persistence directory.")
    vector_collection_name: str = Field(default="transcripts", description="Name of the ChromaDB collection.")
    
    # LLM settings
    llm_provider: str = Field(default="ollama", description="LLM provider ('ollama' or 'openai')")
    ollama_base_url: str = Field(default="http://localhost:11434", description="Base URL for the Ollama API server.")
    default_model: str = Field(default="llama3.1:latest", description="Default Ollama model to use.")
    openai_api_key: str | None = Field(default=None, description="API Key for OpenAI (if used)")
    openai_model: str = Field(default="gpt-4o-mini", description="Default OpenAI model")
    
    # Embedding settings
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5", description="Name or path of the Sentence Transformer model for embeddings.")
    
    # --- External Services ---
    # External Transcript API
    transcript_api_url: Optional[str] = None
    transcript_api_key: Optional[str] = None
    limitless_api_key: str | None = Field(default=None, description="API Key for Limitless integration.")
    
    # OpenAI API Key (Optional)
    # openai_api_key: Optional[str] = None
    # -------------------------

    # LLM Configuration - Consolidate to ollama_base_url
    llm_model_name: str = Field(default="llama3.1", description="Name of the Ollama model to use.")

    # API Server Configuration (for uvicorn)
    api_host: str = Field(default="0.0.0.0", description="Host for the FastAPI server.")
    api_port: int = Field(default=8000, description="Port for the FastAPI server.")
    api_reload: bool = Field(default=True, description="Enable auto-reload for the FastAPI server (development).") # Note: Still recommend False for production/stable testing
    api_log_level: str = Field(default="info", description="Log level for the FastAPI server.")

    # --- Ingestion Configuration ---
    transcript_source_name: str = Field(default="limitless", description="Identifier for the source of transcripts (e.g., 'limitless').")
    raw_response_dir: str = Field(default="./data/raw_limitless_responses", description="Directory to save raw API responses.")

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
        extra='ignore'
    )

def set_ui_ollama_url(url: str):
    """Sets the Ollama Base URL override from the UI."""
    global _ui_set_ollama_url
    # Basic validation could be added here if desired
    _ui_set_ollama_url = url.strip() if url else None
    logger.info(f"UI Override: Ollama Base URL set to: {_ui_set_ollama_url}")

def set_ui_default_model(model_name: str):
    """Sets the Default Model Name override from the UI."""
    global _ui_set_default_model
    _ui_set_default_model = model_name.strip() if model_name else None
    logger.info(f"UI Override: Default Model Name set to: {_ui_set_default_model}")

def get_settings() -> Settings:
    """Get application settings.
    
    Returns:
        Settings: The application settings instance
    """
    settings = Settings()  # Load from .env/env vars

    # Apply UI overrides if they have been set
    if _ui_set_ollama_url is not None:
        logger.debug(f"Applying UI override for ollama_base_url: '{_ui_set_ollama_url}' (Original: '{settings.ollama_base_url}')")
        settings.ollama_base_url = _ui_set_ollama_url
    else:
        logger.debug(f"No UI override for ollama_base_url, using value from env/default: '{settings.ollama_base_url}'")
        
    if _ui_set_default_model is not None:
        logger.debug(f"Applying UI override for default_model: '{_ui_set_default_model}' (Original: '{settings.default_model}')")
        settings.default_model = _ui_set_default_model
    else:
        logger.debug(f"No UI override for default_model, using value from env/default: '{settings.default_model}'")

    return settings 