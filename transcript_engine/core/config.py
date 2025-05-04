"""Configuration module for Transcript Memory Engine.

This module handles all application configuration using pydantic-settings.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional
from pydantic import Field

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
    llm_provider: str = Field(default="ollama", description="LLM provider ('ollama' or 'openai')")
    ollama_base_url: str = Field(default="http://host.docker.internal:11434", description="Base URL for Ollama API (expecting Ollama on host)")
    default_model: str = Field(default="llama3.1", description="Default LLM model to use")
    openai_api_key: str | None = Field(default=None, description="API Key for OpenAI (if used)")
    openai_model: str = Field(default="gpt-4o-mini", description="Default OpenAI model")
    
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
        extra='ignore'
    )

def get_settings() -> Settings:
    """Get application settings.
    
    Returns:
        Settings: The application settings instance
    """
    return Settings() 