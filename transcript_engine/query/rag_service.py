"""Service implementing the Retrieval-Augmented Generation (RAG) pipeline.
"""

import logging
from typing import List, Dict, Any
import sqlite3 # Import sqlite3 for the connection
from datetime import datetime, timezone

from transcript_engine.query.retriever import SimilarityRetriever
from transcript_engine.interfaces.llm_interface import LLMInterface
from transcript_engine.database.models import Chunk
from transcript_engine.database import crud # Import crud

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

    # Simple keywords to detect date-related queries
    DATE_QUERY_KEYWORDS = ["days", "dates", "when", "which day", "what day", "data for"]

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
                            (must contain a 'content' key and optionally 'metadata').
            
        Returns:
            A string containing the concatenated content of the documents.
        """
        if not retrieved_docs:
            return "No relevant context found."
        
        # Format each doc with its start time (if available) and content
        formatted_docs = []
        for doc in retrieved_docs:
            content = doc.get('content', '')
            metadata = doc.get('metadata', {})
            # Assuming metadata *might* contain start_time as ISO string or timestamp
            start_time_val = metadata.get('start_time')
            time_str = "Unknown Time"
            if isinstance(start_time_val, (int, float)):
                try:
                    # Attempt to convert from timestamp
                    dt_obj = datetime.fromtimestamp(start_time_val, tz=timezone.utc)
                    time_str = dt_obj.strftime("%Y-%m-%d %H:%M:%S UTC")
                except (ValueError, TypeError):
                    logger.warning(f"Could not format timestamp: {start_time_val}")
            elif isinstance(start_time_val, str):
                 time_str = start_time_val # Assume it's already formatted if string

            formatted_docs.append(f"[Time: {time_str}]\n{content}")
                
        return "\n\n---\n\n".join(formatted_docs) # Use a separator for clarity

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
        """Answers a user question using the RAG pipeline or by direct DB query for dates.

        Args:
            query_text: The user's question.
            k: The number of chunks to retrieve for context (if RAG is used).

        Returns:
            The LLM-generated answer or a list of dates.
        """
        logger.info(f"Processing query: '{query_text[:100]}...'")

        # --- Check for specific query asking ONLY for available dates --- 
        normalized_query = query_text.lower().strip().replace("?", "")
        # More specific phrases indicating a request for the list of dates
        date_list_phrases = [
            "what days do you have transcript data for",
            "what days do you have data for",
            "which days do you have data for",
            "what dates do you have data for",
            "which dates do you have data for",
            "list available dates",
            "list transcript dates",
            "show transcript dates",
            "available dates",
            "available days"
        ]
        # Check for an exact or very close match to these specific phrases
        # This is a simple heuristic, more robust NLP could be used
        is_direct_date_list_query = any(phrase == normalized_query for phrase in date_list_phrases)

        if is_direct_date_list_query:
            logger.info("Detected query asking specifically for available transcript dates. Querying database directly.")
            try:
                # Import get_db locally within the method to avoid circular import
                from transcript_engine.core.dependencies import get_db
                db_conn = get_db()
                distinct_dates = crud.get_distinct_transcript_dates(db_conn)
                if distinct_dates:
                    formatted_dates = [d.strftime("%Y-%m-%d") for d in distinct_dates]
                    formatted_dates.sort()
                    date_list_str = "\n".join([f"- {d}" for d in formatted_dates])
                    return f"I have transcript data available for the following dates:\n{date_list_str}"
                else:
                    return "I could not find any dates with transcript data in the database."
            except Exception as e:
                logger.error(f"Error querying distinct dates from database: {e}", exc_info=True)
                return "I encountered an error while trying to determine the available transcript dates."
        # ---------------------------------------------------------------

        # --- If not a specific date list query, proceed with standard RAG --- 
        logger.info("Proceeding with standard RAG pipeline.")
        
        # 1. Retrieve relevant chunks
        retrieved_chunks = self.retriever.retrieve(query_text=query_text, k=k)
        
        # --- TEMPORARY DEBUG LOGGING --- 
        if retrieved_chunks:
            logger.debug(f"DEBUG: Metadata of first retrieved chunk: {retrieved_chunks[0].get('metadata', {})}")
        else:
            logger.debug("DEBUG: No chunks retrieved.")
        # --- END TEMPORARY DEBUG LOGGING --- 
        
        if not retrieved_chunks:
            logger.warning("No chunks retrieved for query. Cannot generate context-based answer.")
            return "I couldn't find any relevant information in the transcripts to answer your question."
        
        # 3. Format Context
        context_str = self._format_context(retrieved_chunks)
        logger.debug(f"Formatted context provided to LLM:\n------ START CONTEXT ------\n{context_str}\n------ END CONTEXT ------")

        # 4. Generate Prompt
        prompt = self._create_prompt(question=query_text, context=context_str)
        logger.debug(f"Generated prompt:\n------ START PROMPT ------\n{prompt}\n------ END PROMPT ------")

        # 5. Send to LLM
        logger.debug("Sending prompt to LLM...")
        try:
            llm_response = self.llm.generate(prompt=prompt)
            logger.info("Received response from LLM.")
            logger.debug(f"LLM Response (first 100 chars): {llm_response[:100]}...")
            return llm_response
        except Exception as e:
            logger.error(f"Error generating LLM response: {e}", exc_info=True)
            llm_response = "I encountered an error while trying to generate an answer."
            return llm_response 