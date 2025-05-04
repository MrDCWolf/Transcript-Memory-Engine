"""Implementation of the LLMInterface using the Ollama API.
"""

import logging
import ollama
from typing import List, Dict, Any, cast

from transcript_engine.interfaces.llm_interface import LLMInterface
from transcript_engine.database.models import ChatMessage
from transcript_engine.core.config import Settings

logger = logging.getLogger(__name__)

class OllamaClient(LLMInterface):
    """Connects to a local Ollama instance to provide LLM capabilities.

    Implements the LLMInterface protocol.
    """

    def __init__(self, settings: Settings):
        """Initializes the Ollama client.

        Args:
            settings: The application settings containing Ollama configuration.
        """
        self.client = ollama.Client(host=settings.ollama_base_url)
        self.default_model = settings.default_model
        logger.info(f"Ollama client initialized for host: {settings.ollama_base_url}")

    def generate(self, prompt: str, model: str | None = None, **kwargs: Any) -> str:
        """Generates text using the Ollama /api/generate endpoint.

        Args:
            prompt: The input prompt.
            model: The model to use (defaults to settings.default_model).
            **kwargs: Additional options for ollama.generate (e.g., temperature).

        Returns:
            The generated text response.
            
        Raises:
            ollama.ResponseError: If the Ollama API returns an error.
            Exception: For other unexpected errors.
        """
        target_model = model or self.default_model
        try:
            logger.debug(f"Generating text with model '{target_model}'. Prompt: '{prompt[:50]}...'")
            response = self.client.generate(
                model=target_model,
                prompt=prompt,
                options=kwargs.get("options", {}),
                stream=False # Ensure we get the full response
            )
            generated_text = response.get('response', '').strip()
            logger.debug(f"Generated text response (first 50 chars): '{generated_text[:50]}...'")
            return generated_text
        except ollama.ResponseError as e:
            logger.error(f"Ollama API error during generation: {e.status_code} - {e.error}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during Ollama generation: {e}", exc_info=True)
            raise

    def chat(self, messages: List[ChatMessage], model: str | None = None, **kwargs: Any) -> ChatMessage:
        """Generates a chat response using the Ollama /api/chat endpoint.

        Args:
            messages: A list of ChatMessage Pydantic models.
            model: The model to use (defaults to settings.default_model).
            **kwargs: Additional options for ollama.chat (e.g., temperature).

        Returns:
            A ChatMessage Pydantic model representing the assistant's response.
            
        Raises:
            ollama.ResponseError: If the Ollama API returns an error.
            Exception: For other unexpected errors.
        """
        target_model = model or self.default_model
        
        # Convert ChatMessage models to dictionaries expected by ollama library
        # Using .model_dump() is standard for Pydantic v2+
        message_dicts = [msg.model_dump() for msg in messages]
        
        try:
            logger.debug(f"Generating chat response with model '{target_model}'. History length: {len(message_dicts)}")
            response = self.client.chat(
                model=target_model,
                messages=message_dicts,
                options=kwargs.get("options", {}),
                stream=False # Ensure we get the full response
            )
            assistant_message = response.get('message', {})
            role = assistant_message.get('role', 'assistant')
            content = assistant_message.get('content', '').strip()
            logger.debug(f"Generated chat response (first 50 chars): '{content[:50]}...'")
            # Return the proper Pydantic model
            return ChatMessage(role=role, content=content) 
        except ollama.ResponseError as e:
            logger.error(f"Ollama API error during chat: {e.status_code} - {e.error}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error during Ollama chat: {e}", exc_info=True)
            raise 