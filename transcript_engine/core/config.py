"""Configuration module for Transcript Memory Engine.

This module handles all application configuration using pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    """Application settings class.
    
    This class defines all configuration settings for the application.
    Settings are loaded from environment variables with appropriate defaults.
    """
    
    # Application settings
    environment: str = "development"
    debug: bool = False
    
    # Database settings
    database_url: str = "sqlite:///./data/transcript_engine.db"
    
    # Vector store settings
    vector_store_path: str = "./data/vector_store"
    
    # LLM settings
    ollama_base_url: str = "http://localhost:11434"
    default_model: str = "llama2"
    
    # Embedding settings
    embedding_model: str = "BAAI/bge-small-en-v1.5"
    
    # --- External Services ---
    # External Transcript API
    transcript_api_url: Optional[str] = None
    transcript_api_key: Optional[str] = None
    limitless_api_key: Optional[str] = None
    
    # OpenAI API Key (Optional)
    # openai_api_key: Optional[str] = None
    # -------------------------

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=True,
    )

def get_settings() -> Settings:
    """Get application settings.
    
    Returns:
        Settings: The application settings instance
    """
    return Settings() 