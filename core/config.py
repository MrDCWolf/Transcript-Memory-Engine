from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
import os

class Settings(BaseSettings):
    """Application configuration settings."""
    # General
    app_name: str = "Transcript Memory Engine"

    # Database
    # Default to a relative path within the project structure
    # Use Field to provide description for documentation
    database_url: str = Field(
        default="sqlite:///./data/transcript_engine.db",
        description="SQLite database connection URL (relative path allowed)"
    )

    # LLM Configuration
    llm_provider: str = Field(default="ollama", description="LLM provider ('ollama' or 'openai')")
    ollama_base_url: str = Field(default="http://host.docker.internal:11434", description="Base URL for Ollama API")
    default_model: str = Field(default="llama3", description="Default LLM model to use")
    openai_api_key: str | None = Field(default=None, description="API Key for OpenAI (if used)")
    openai_model: str = Field(default="gpt-4o-mini", description="Default OpenAI model")

    # Embedding Configuration
    embedding_provider: str = Field(default="bge_local", description="Embedding provider ('bge_local', 'openai', 'stub')")
    bge_model_name: str = Field(default="BAAI/bge-small-en-v1.5", description="Sentence Transformer model for BGE")
    embedding_dimension: int | None = Field(default=384, description="Output dimension of embedding model (e.g., 384 for bge-small, 1024 for bge-base)") # Auto-detected usually

    # Vector Store Configuration
    vector_store_provider: str = Field(default="chroma", description="Vector store provider ('chroma')")
    chroma_persist_directory: str = Field(default="./data/chroma_db", description="Directory to persist ChromaDB data")
    chroma_collection_name: str = Field(default="transcripts", description="Name of the Chroma collection")

    # Limitless API (Optional)
    limitless_api_key: str | None = Field(default=None, description="API Key for Limitless transcript source") # Default to None

    # Chunking Configuration
    chunk_size: int = Field(default=1000, description="Target size for text chunks (in characters)")
    chunk_overlap: int = Field(default=100, description="Overlap between text chunks (in characters)")


    model_config = SettingsConfigDict(
        env_prefix='', # Explicitly state no prefix
        env_file='.env',
        env_file_encoding='utf-8',
        extra='ignore' # Allow extra fields from environment/dotenv
    )

def get_settings() -> Settings:
    """Get the application settings instance."""
    # This allows caching settings if needed in the future
    return Settings() 