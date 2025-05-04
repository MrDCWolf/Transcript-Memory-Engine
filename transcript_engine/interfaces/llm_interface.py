"""Interface definition for Large Language Model (LLM) services.
"""

from typing import Protocol, List, Dict, Any, runtime_checkable

# Import the proper ChatMessage model
from transcript_engine.database.models import ChatMessage

@runtime_checkable
class LLMInterface(Protocol):
    """A protocol defining the standard interface for LLM interactions.

    This ensures that different LLM backends (Ollama, OpenAI, etc.)
    can be used interchangeably.
    """

    def generate(self, prompt: str, model: str | None = None, **kwargs: Any) -> str:
        """Generates a text completion based on a single prompt.

        Args:
            prompt: The input text prompt.
            model: The specific model to use (optional, uses default if None).
            **kwargs: Additional keyword arguments for the LLM backend.

        Returns:
            The generated text completion.
        """
        ...

    def chat(self, messages: List[ChatMessage], model: str | None = None, **kwargs: Any) -> ChatMessage:
        """Generates a response based on a conversation history (list of messages).

        Args:
            messages: A list of ChatMessage objects representing the conversation history.
            model: The specific model to use (optional, uses default if None).
            **kwargs: Additional keyword arguments for the LLM backend.

        Returns:
            A ChatMessage object representing the assistant's response.
        """
        ... 