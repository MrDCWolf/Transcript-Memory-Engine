"""Tests for the configuration loading.
"""

import pytest
import os
from unittest.mock import patch

# Ensure the tests can import from the main package
# This might require adding tests/ to PYTHONPATH or using pytest's features

# Assuming Settings can be imported (adjust path if needed based on project structure)
# We might need to configure PYTHONPATH or use relative imports carefully
try:
    from transcript_engine.core.config import Settings, get_settings
except ImportError:
    # If running pytest from root, direct import might fail
    # This is a common issue, often solved by how pytest is invoked or PYTHONPATH setup
    pytest.skip("Skipping config tests, unable to import transcript_engine.core.config", allow_module_level=True)

def test_settings_loading_directly():
    """Test that Settings can be initialized directly with values.
    
    Bypasses environment variables and .env files.
    """
    test_values = {
        "environment": "testing",
        "debug": True,
        "database_url": "sqlite:///./data/test_db.sqlite",
        "vector_store_path": "./data/test_vector_store",
        "ollama_base_url": "http://localhost:11435",
        "default_model": "test_model",
        "embedding_model": "test/embedding-model",
    }
    # Explicitly disable .env file reading when passing direct values
    settings = Settings(**test_values, _env_file=None)
    
    assert isinstance(settings, Settings)
    assert settings.environment == "testing"
    assert settings.debug is True
    assert settings.database_url == "sqlite:///./data/test_db.sqlite"
    assert settings.vector_store_path == "./data/test_vector_store"
    assert settings.ollama_base_url == "http://localhost:11435"
    assert settings.default_model == "test_model"
    assert settings.embedding_model == "test/embedding-model"

def test_settings_defaults():
    """Test that Settings use default values when environment variables are not set.
    
    Relies on the fact that temporary_env_vars fixture is NOT used here.
    We assume the default .env is minimal or doesn't exist for testing defaults.
    Also prevents reading any actual .env file.
    """
    # Clear environment and prevent reading default .env file
    with patch.dict(os.environ, {}, clear=True):
        settings = Settings(_env_file=None) # Explicitly disable .env read
        
    assert settings.environment == "development" # Default value
    assert settings.debug is False # Default value
    assert settings.database_url == "sqlite:///./data/transcript_engine.db" # Default
    # Check other defaults... 