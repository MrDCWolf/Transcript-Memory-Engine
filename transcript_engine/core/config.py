"""Configuration module for Transcript Memory Engine.

This module handles all application configuration using pydantic-settings,
with support for persistent UI overrides via a JSON file.
"""

import logging
import json
from pathlib import Path
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional, Dict, Any, Union, List
from pydantic import Field

# Explicitly load .env file BEFORE BaseSettings reads environment variables
load_dotenv()

logger = logging.getLogger(__name__)

# --- Persistent UI Overrides ---
# Use a JSON file to store settings changed via the UI
UI_SETTINGS_FILENAME = "ui_settings.json"
# Assume 'data' directory is adjacent to 'transcript_engine' or at project root
# A more robust way might involve getting the project root dynamically
# For now, let's assume it's in a 'data' subdir relative to where app runs
# Or use an absolute path if more reliable. Let's try relative first.
DATA_DIR = Path("./data") 
UI_SETTINGS_PATH = DATA_DIR / UI_SETTINGS_FILENAME

def _load_ui_overrides() -> Dict[str, Any]:
    """Loads UI override settings from the JSON file."""
    if UI_SETTINGS_PATH.exists():
        try:
            with open(UI_SETTINGS_PATH, 'r') as f:
                overrides = json.load(f)
                logger.debug(f"Loaded UI overrides from {UI_SETTINGS_PATH}: {overrides}")
                return overrides
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Error reading UI settings file {UI_SETTINGS_PATH}: {e}", exc_info=True)
    return {}

def _save_ui_overrides(overrides: Dict[str, Any]):
    """Saves UI override settings to the JSON file."""
    try:
        DATA_DIR.mkdir(parents=True, exist_ok=True) # Ensure data directory exists
        with open(UI_SETTINGS_PATH, 'w') as f:
            json.dump(overrides, f, indent=2)
        logger.debug(f"Saved UI overrides to {UI_SETTINGS_PATH}: {overrides}")
    except IOError as e:
        logger.error(f"Error writing UI settings file {UI_SETTINGS_PATH}: {e}", exc_info=True)
# -----------------------------

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
    
    # Context Window Settings (Defaults loaded from .env, can be overridden by UI)
    model_context_window: int = Field(default=8192, description="Maximum context window size for the selected LLM in tokens.")
    answer_buffer_tokens: int = Field(default=1000, description="Number of tokens to reserve for the LLM's answer.")
    context_target_tokens: int | None = Field(default=None, description="Optional target token limit for context (must be <= model_context_window - answer_buffer). Useful for performance tuning.")
    
    # Embedding settings
    embedding_model: str = Field(default="BAAI/bge-small-en-v1.5", description="Name or path of the Sentence Transformer model for embeddings.")
    
    # --- Feature: Actionable Items Timeframes ---
    TIMEFRAME_BOUNDARIES: Dict[str, tuple[int, int]] = Field(
        default={
            "morning": (6, 12),  # 6:00 AM to 11:59 AM
            "afternoon": (12, 18), # 12:00 PM to 5:59 PM
            "evening": (18, 24),   # 6:00 PM to 11:59 PM (24 is exclusive end for hour)
        },
        description="Hour boundaries for defining morning, afternoon, evening. Start hour inclusive, end hour exclusive."
    )
    
    # --- Cloud AI API Settings (for structured data extraction) ---
    OPENAI_API_KEY: Optional[str] = Field(
        default=None, 
        description="API Key for OpenAI (used for structured data extraction by actionables feature)."
    )
    OPENAI_CHAT_MODEL_NAME: str = Field(
        default="gpt-4o-mini", # Example, user can override
        description="OpenAI chat model to use for structured data extraction (e.g., gpt-4o, gpt-4o-mini, gpt-3.5-turbo)."
    )
    
    # --- Google OAuth Settings ---
    GOOGLE_CLIENT_SECRET_JSON_PATH: str = Field(
        default="client_secret.json", 
        description="Path to the Google OAuth client_secret.json file (relative to project root)."
    )
    GOOGLE_OAUTH_TOKENS_PATH: str = Field(
        default="data/google_oauth_tokens.json",
        description="Path to store user's Google OAuth tokens (relative to project root)."
    )
    GOOGLE_OAUTH_REDIRECT_URI: str = Field(
        default="http://localhost:8000/auth/google/callback",
        description="OAuth redirect URI. Must match one configured in Google Cloud Console."
    )
    GOOGLE_CALENDAR_API_SCOPES: List[str] = Field(
        default=["https://www.googleapis.com/auth/calendar.events"],
        description="Scopes for Google Calendar API access."
    )
    GOOGLE_TASKS_API_SCOPES: List[str] = Field(
        default=["https://www.googleapis.com/auth/tasks"],
        description="Scopes for Google Tasks API access."
    )
    
    # --- External Services ---
    # External Transcript API
    transcript_api_url: Optional[str] = None
    transcript_api_key: Optional[str] = None
    limitless_api_key: str | None = Field(default=None, description="API Key for Limitless integration.")
    
    # OpenAI API Key (Optional)
    # openai_api_key: Optional[str] = None
    # -------------------------

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
    """Sets the Ollama Base URL override from the UI and persists it."""
    # Basic validation could be added here if desired
    clean_url = url.strip() if url else None
    if clean_url:
        overrides = _load_ui_overrides()
        overrides['ollama_base_url'] = clean_url
        _save_ui_overrides(overrides)
        logger.info(f"UI Override Persisted: Ollama Base URL set to: {clean_url}")
    else:
         # Handle potential removal of override? Or just log?
         logger.warning("Attempted to set empty Ollama Base URL override.")

def set_ui_default_model(model_name: str):
    """Sets the Default Model Name override from the UI and persists it."""
    clean_model_name = model_name.strip() if model_name else None
    if clean_model_name:
        overrides = _load_ui_overrides()
        overrides['default_model'] = clean_model_name
        _save_ui_overrides(overrides)
        logger.info(f"UI Override Persisted: Default Model Name set to: {clean_model_name}")
    else:
        logger.warning("Attempted to set empty Default Model Name override.")

def set_ui_model_context_window(value: int | None):
    """Sets the Model Context Window override from the UI and persists it."""
    if value is not None and value > 0:
        overrides = _load_ui_overrides()
        overrides['model_context_window'] = value
        _save_ui_overrides(overrides)
        logger.info(f"UI Override Persisted: Model Context Window set to: {value}")
    elif 'model_context_window' in _load_ui_overrides(): # Handle removal if needed
        overrides = _load_ui_overrides()
        del overrides['model_context_window']
        _save_ui_overrides(overrides)
        logger.info("UI Override Removed: Model Context Window reverted to default.")

def set_ui_answer_buffer_tokens(value: int | None):
    """Sets the Answer Buffer Tokens override from the UI and persists it."""
    if value is not None and value >= 0:
        overrides = _load_ui_overrides()
        overrides['answer_buffer_tokens'] = value
        _save_ui_overrides(overrides)
        logger.info(f"UI Override Persisted: Answer Buffer Tokens set to: {value}")
    elif 'answer_buffer_tokens' in _load_ui_overrides(): # Handle removal
        overrides = _load_ui_overrides()
        del overrides['answer_buffer_tokens']
        _save_ui_overrides(overrides)
        logger.info("UI Override Removed: Answer Buffer Tokens reverted to default.")

def set_ui_context_target_tokens(value: int | None):
    """Sets the Context Target Tokens override from the UI and persists it."""
    overrides = _load_ui_overrides()
    if value is not None and value > 0:
        overrides['context_target_tokens'] = value
        _save_ui_overrides(overrides)
        logger.info(f"UI Override Persisted: Context Target Tokens set to: {value}")
    elif value is None and 'context_target_tokens' in overrides:
        # If explicitly set to None/empty in UI, remove the override
        del overrides['context_target_tokens']
        _save_ui_overrides(overrides)
        logger.info("UI Override Removed: Context Target Tokens reverted to default.")
    elif value is not None: # Log invalid input but don't save
        logger.warning(f"Attempted to set invalid Context Target Tokens override: {value}")

def get_settings() -> Settings:
    """Get application settings, applying persisted UI overrides.
    
    Loads base settings from environment/.env, then applies overrides
    found in data/ui_settings.json.
    
    Returns:
        Settings: The application settings instance with overrides applied.
    """
    settings = Settings()  # Load from .env/env vars

    # Load persisted UI overrides
    ui_overrides = _load_ui_overrides()
    
    # Apply UI overrides if they exist in the JSON file
    # Use a helper to avoid repetition
    def apply_override(key: str, setting_attr: str):
        if key in ui_overrides:
            original_value = getattr(settings, setting_attr)
            override_value = ui_overrides[key]
            # Try to cast override value to the correct type if needed (e.g., str -> int)
            try:
                field_type = Settings.__annotations__.get(setting_attr)
                # Handle Optional types if necessary, e.g., Optional[int]
                is_optional = getattr(field_type, '__origin__', None) is Union and type(None) in getattr(field_type, '__args__', ()) 
                base_type = field_type
                if is_optional:
                   # Get the non-None type from Optional[T]
                   base_type = next((t for t in getattr(field_type, '__args__', ()) if t is not type(None)), None)
                
                if base_type is int and isinstance(override_value, str):
                     override_value = int(override_value)
                # Add more type checks/casts as needed (float, bool etc.)
                    
                if override_value != original_value:
                    logger.debug(f"Applying UI override for {setting_attr}: '{override_value}' (Original: '{original_value}')")
                    setattr(settings, setting_attr, override_value)
                else:
                    logger.debug(f"UI override for {setting_attr} matches env/default: '{original_value}'")
            except (ValueError, TypeError) as e:
                logger.warning(f"Could not apply UI override for {setting_attr}: Invalid value '{ui_overrides[key]}' ({e}). Using default: {getattr(settings, setting_attr)}")
        else:
            logger.debug(f"No persisted UI override for {setting_attr}, using value from env/default: '{getattr(settings, setting_attr)}'")

    apply_override('ollama_base_url', 'ollama_base_url')
    apply_override('default_model', 'default_model')
    apply_override('model_context_window', 'model_context_window')
    apply_override('answer_buffer_tokens', 'answer_buffer_tokens')
    apply_override('context_target_tokens', 'context_target_tokens')
    
    return settings 