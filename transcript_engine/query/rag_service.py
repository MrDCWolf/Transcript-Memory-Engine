"""Service implementing the Retrieval-Augmented Generation (RAG) pipeline.
"""

import logging
from typing import List, Dict, Any

from transcript_engine.query.retriever import SimilarityRetriever
from transcript_engine.interfaces.llm_interface import LLMInterface
from transcript_engine.database.models import Chunk

logger = logging.getLogger(__name__)

class RAGService:
    """Orchestrates the RAG process: retrieve -> augment -> generate.
    """

    DEFAULT_PROMPT_TEMPLATE = (
        "You are a helpful assistant answering questions based on the following transcript context.\n"
        "Answer the user's question accurately using ONLY the provided context.\n"
        "If the answer is not found in the context, state that clearly.\n\n"
        "Context:\n"
        "-------\n"
        "{context}\n"
        "-------\n\n"
        "Question: {question}\n"
        "Answer:"
    )

    def __init__(self, retriever: SimilarityRetriever, llm: LLMInterface):
        """Initializes the RAGService.

        Args:
            retriever: An instance of SimilarityRetriever (or compatible).
            llm: An instance conforming to LLMInterface.
        """
        self.retriever = retriever
        self.llm = llm
        logger.info("RAGService initialized.")

    def _format_context(self, retrieved_docs: List[Dict[str, Any]]) -> str:
        """Formats the retrieved document dictionaries into a single context string.
        
        Args:
            retrieved_docs: A list of dictionaries, each representing a retrieved document
                            (must contain a 'content' key).
            
        Returns:
            A string containing the concatenated content of the documents.
        """
        if not retrieved_docs:
            return "No relevant context found."
        # Extract content from each dictionary
        return "\n\n".join([doc.get('content', '') for doc in retrieved_docs])

    def _create_prompt(self, question: str, context: str) -> str:
        """Creates the final prompt for the LLM using a template.

        Args:
            question: The user's original question.
            context: The formatted context string from retrieved chunks.
        
        Returns:
            The fully formatted prompt string.
        """
        return self.DEFAULT_PROMPT_TEMPLATE.format(context=context, question=question)

    def answer_question(self, query_text: str, k: int = 5) -> str:
        """Answers a user question using the RAG pipeline.

        Args:
            query_text: The user's question.
            k: The number of chunks to retrieve for context.

        Returns:
            The LLM-generated answer based on the retrieved context.
        """
        logger.info(f"Processing RAG query: '{query_text[:100]}...'")
        
        # 1. Retrieve relevant chunks
        retrieved_chunks = self.retriever.retrieve(query_text=query_text, k=k)
        
        if not retrieved_chunks:
            logger.warning("No chunks retrieved for query. Cannot generate context-based answer.")
            # Optionally, could ask LLM without context, or return a specific message
            return "I couldn't find any relevant information in the transcripts to answer your question."
        
        # 2. Format context and create prompt
        context_str = self._format_context(retrieved_chunks)
        prompt = self._create_prompt(question=query_text, context=context_str)
        logger.debug(f"Generated prompt for LLM (length: {len(prompt)}): \n------ START PROMPT ------\n{prompt}\n------ END PROMPT ------") # Log full prompt for debugging
        
        # 3. Generate answer using LLM
        try:
            logger.debug("Sending prompt to LLM...")
            llm_response = self.llm.generate(prompt=prompt)
            logger.info("Received response from LLM.")
            return llm_response
        except Exception as e:
            logger.error(f"Error generating LLM response: {e}", exc_info=True)
            return "I encountered an error while trying to generate an answer." 