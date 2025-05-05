"""Service implementing the Retrieval-Augmented Generation (RAG) pipeline.
"""

import logging
from typing import List, Dict, Any, Tuple
import sqlite3 # Import sqlite3 for the connection
from datetime import datetime, timezone
import tiktoken # Import tiktoken

from transcript_engine.query.retriever import SimilarityRetriever
from transcript_engine.interfaces.llm_interface import LLMInterface
from transcript_engine.database.models import Chunk, ChatMessage # Assuming ChatMessage is needed for history
from transcript_engine.database import crud # Import crud
from transcript_engine.core.config import get_settings # Import get_settings

logger = logging.getLogger(__name__)

# Update the System Prompt Template
SYSTEM_PROMPT_TEMPLATE = """System: You are an AI assistant specialized in analyzing conversation transcripts to answer user questions thoroughly. Your task is to carefully review the user's question, the chat history, and the provided transcript excerpts to synthesize a comprehensive, well-structured answer.

**IMPORTANT RULES:**
- **Synthesize Information:** Combine insights from *all* relevant transcript excerpts and chat history to directly answer the user's question. Do not simply list excerpts.
- **Identify Key Themes:** Structure your answer around the main themes or sub-topics found in the relevant excerpts related to the question. Use clear headings or distinct paragraphs for different themes if appropriate.
- **Include Specific Details & Quotes:** Incorporate specific details, examples, and 1-2 concise, impactful quotes from the transcripts to support your points. Cite the source conversation/timestamp if easily available in the metadata provided with the excerpt, but prioritize flow over excessive citation.
- **Base Answer *Solely* on Provided Text:** Do *not* use any external knowledge. Your entire answer must be derived from the 'Chat History' and 'Transcript Excerpts' provided below.
- **Handle Missing Information:** If the answer cannot be synthesized from the provided text, state that clearly (e.g., "Based on the provided transcripts, I don't have enough information to answer that specific point."). Do not speculate.
- **Concluding Highlights (Optional but Recommended):** If appropriate for the question, end your response with a brief bulleted list summarizing the key takeaways or highlights related to the query.
- **Tone:** Be informative, objective, and helpful.
"""

class RAGService:
    """Orchestrates the RAG process: retrieve -> augment -> generate.
    """

    def __init__(self, retriever: SimilarityRetriever, llm: LLMInterface):
        """Initializes the RAGService.

        Args:
            retriever: An instance of SimilarityRetriever (or compatible).
            llm: An instance conforming to LLMInterface.
        """
        self.retriever = retriever
        self.llm = llm
        # Initialize tokenizer once
        try:
            self.tokenizer = tiktoken.get_encoding("cl100k_base")
        except Exception:
            logger.warning("cl100k_base tokenizer not found, falling back to gpt2.")
            self.tokenizer = tiktoken.get_encoding("gpt2")
        logger.info(f"RAGService initialized with tokenizer: {self.tokenizer.name}")

    def answer_question(self, query_text: str, k: int = 20) -> Tuple[str, List[Dict[str, Any]]]:
        """Answers a user question using RAG, dynamically managing context window.

        Args:
            query_text: The user's question.
            k: The *initial* number of chunks to retrieve for potential inclusion.

        Returns:
            A tuple containing:
                - The LLM-generated answer string.
                - The list of chunk dictionaries *actually included* in the LLM prompt context.
        """
        logger.info(f"Processing query: '{query_text[:100]}...' (Retrieving initial k={k})")
        settings = get_settings()

        # --- Date Query Logic (remains the same) --- 
        normalized_query = query_text.lower().strip().replace("?", "")
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
        is_direct_date_list_query = any(phrase == normalized_query for phrase in date_list_phrases)

        if is_direct_date_list_query:
            logger.info("Detected query asking specifically for available transcript dates. Querying database directly.")
            try:
                from transcript_engine.core.dependencies import get_db
                db_conn = get_db()
                distinct_dates = crud.get_distinct_transcript_dates(db_conn)
                if distinct_dates:
                    formatted_dates = sorted([d.strftime("%Y-%m-%d") for d in distinct_dates])
                    date_list_str = "\n".join([f"- {d}" for d in formatted_dates])
                    return f"I have transcript data available for the following dates:\n{date_list_str}", []
                else:
                    return "I could not find any dates with transcript data in the database.", []
            except Exception as e:
                logger.error(f"Error querying distinct dates from database: {e}", exc_info=True)
                return "I encountered an error while trying to determine the available transcript dates.", []
        # ---------------------------------------------------------------

        # --- RAG Pipeline with Token Budgeting --- 
        logger.info("Proceeding with standard RAG pipeline with token budgeting.")

        # 1. Retrieve *initial* pool of relevant chunks (expecting List[Dict[str, Any]])
        retrieved_chunks: List[Dict[str, Any]] = self.retriever.retrieve(query_text=query_text, k=k)
        
        if not retrieved_chunks:
            logger.warning("No chunks retrieved for query. Cannot generate context-based answer.")
            return "I couldn't find any relevant information in the transcripts to answer your question.", []

        # 2. Load Chat History (Placeholder - implement history loading if needed)
        # chat_history: List[ChatMessage] = crud.get_chat_history(db_conn, session_id) # Example
        chat_history: List[ChatMessage] = [] # Keep placeholder for now

        # 3. Calculate Token Budget
        max_context_tokens = settings.model_context_window
        answer_buffer = settings.answer_buffer_tokens
        # Use target tokens if set and valid, otherwise use max allowed by window & buffer
        target_limit = max_context_tokens - answer_buffer
        if settings.context_target_tokens and settings.context_target_tokens > 0:
            target_tokens = min(settings.context_target_tokens, target_limit)
            logger.debug(f"Using CONTEXT_TARGET_TOKENS: {target_tokens}")
        else:
            target_tokens = target_limit
            logger.debug(f"Using MODEL_CONTEXT_WINDOW derived target: {target_tokens}")

        # Tokenize fixed parts
        system_prompt_tokens = len(self.tokenizer.encode(SYSTEM_PROMPT_TEMPLATE))
        query_tokens = len(self.tokenizer.encode(f"**Current Question:**\n{query_text}"))
        # Estimate tokens for formatting (headers, separators, etc.) - adjust as needed
        formatting_tokens_estimate = 150 # Increased estimate slightly
        answer_prefix_tokens = len(self.tokenizer.encode("\n**Synthesized Answer:**"))

        fixed_tokens = system_prompt_tokens + query_tokens + formatting_tokens_estimate + answer_prefix_tokens
        available_tokens = target_tokens - fixed_tokens
        logger.debug(f"Token Budget: Max={max_context_tokens}, Target={target_tokens}, Buffer={answer_buffer}, Fixed={fixed_tokens}, Available={available_tokens}")

        if available_tokens <= 0:
            logger.warning(f"Fixed prompt parts ({fixed_tokens} tokens) exceed available budget ({target_tokens} tokens). Context will be empty.")
            available_tokens = 0 

        # 4. Select History (Prioritize newest)
        selected_history: List[ChatMessage] = []
        if chat_history:
            current_history_tokens = 0
            for msg in reversed(chat_history):
                msg_text = f"{msg.role.capitalize()}: {msg.content}\n"
                msg_tokens = len(self.tokenizer.encode(msg_text))
                
                # Check budget *before* adding
                if current_history_tokens + msg_tokens <= available_tokens:
                    current_history_tokens += msg_tokens
                    selected_history.insert(0, msg) # Add to beginning to maintain order
                else:
                    logger.debug(f"History budget exceeded. Stopped after adding {len(selected_history)} messages ({current_history_tokens} tokens).")
                    break 
            available_tokens -= current_history_tokens
            logger.debug(f"Selected {len(selected_history)} history messages ({current_history_tokens} tokens). Remaining budget: {available_tokens}")

        # 5. Select Chunks (Prioritize most relevant)
        selected_chunks: List[Dict[str, Any]] = []
        current_chunk_tokens = 0
        for i, chunk_dict in enumerate(retrieved_chunks):
            metadata = chunk_dict.get('metadata', {}) 
            content = chunk_dict.get('content', '')
            transcript_id = metadata.get('transcript_id', 'N/A')
            start_time = metadata.get('start_time', 'N/A')

            # Format start_time for prompt consistency
            formatted_start_time = start_time
            if isinstance(start_time, (int, float)):
                try:
                    dt_obj = datetime.fromtimestamp(start_time, tz=timezone.utc)
                    formatted_start_time = dt_obj.strftime("%Y-%m-%d %H:%M:%S UTC")
                except (ValueError, TypeError):
                    formatted_start_time = "Invalid Timestamp"
            elif not isinstance(start_time, str):
                formatted_start_time = str(start_time)

            # Format chunk text as it will appear in the prompt for token calculation
            chunk_prefix = f"*{i+1}. (Transcript ID: {transcript_id}, Time: {formatted_start_time}):*\n"
            chunk_separator = "\n---\n"
            chunk_full_text_for_calc = chunk_prefix + content + chunk_separator
            chunk_tokens = len(self.tokenizer.encode(chunk_full_text_for_calc))

            # Check budget *before* adding
            if current_chunk_tokens + chunk_tokens <= available_tokens:
                current_chunk_tokens += chunk_tokens
                selected_chunks.append(chunk_dict)
            else:
                logger.debug(f"Chunk budget exceeded. Stopped after adding {len(selected_chunks)} chunks ({current_chunk_tokens} tokens). Tried to add chunk {i+1} ({chunk_tokens} tokens). Budget left: {available_tokens}")
                break # Stop adding chunks
                
        available_tokens -= current_chunk_tokens # This might be negative if formatting estimate was low
        logger.debug(f"Selected {len(selected_chunks)} chunks ({current_chunk_tokens} tokens). Final remaining budget: {available_tokens}")

        # 6. Construct Final Prompt using selected items
        prompt_parts = []
        prompt_parts.append(SYSTEM_PROMPT_TEMPLATE)

        if selected_history:
            history_str_parts = ["---", "**Chat History:**"]
            for msg in selected_history:
                history_str_parts.append(f"{msg.role.capitalize()}: {msg.content}")
            prompt_parts.append("\n".join(history_str_parts))

        context_str_parts = ["---", "**Transcript Excerpts Used for Context:**"]
        if selected_chunks:
            for i, chunk_dict in enumerate(selected_chunks): # Iterate selected chunks
                metadata = chunk_dict.get('metadata', {}) 
                content = chunk_dict.get('content', '')
                transcript_id = metadata.get('transcript_id', 'N/A')
                start_time = metadata.get('start_time', 'N/A')
                formatted_start_time = start_time # Reformat again for final prompt
                if isinstance(start_time, (int, float)):
                    try:
                        dt_obj = datetime.fromtimestamp(start_time, tz=timezone.utc)
                        formatted_start_time = dt_obj.strftime("%Y-%m-%d %H:%M:%S UTC")
                    except (ValueError, TypeError): formatted_start_time = "Invalid Timestamp"
                elif not isinstance(start_time, str): formatted_start_time = str(start_time)

                context_str_parts.append(f"*{i+1}. (Transcript ID: {transcript_id}, Time: {formatted_start_time}):*\n{content}")
                context_str_parts.append("---") 
                
            if context_str_parts[-1] == "---": context_str_parts.pop()
        else:
            context_str_parts.append("No relevant transcript excerpts could fit in the context window.") # More specific message
            
        prompt_parts.append("\n".join(context_str_parts))

        prompt_parts.append("---")
        prompt_parts.append(f"**Current Question:**\n{query_text}")
        prompt_parts.append("\n**Synthesized Answer:**")

        final_prompt = "\n\n".join(prompt_parts)
        final_prompt_tokens = len(self.tokenizer.encode(final_prompt))
        logger.debug(f"Final prompt token count: {final_prompt_tokens} (Budget Available: {target_tokens - fixed_tokens + answer_prefix_tokens}) Limit: {target_tokens + answer_prefix_tokens}) ")
        if final_prompt_tokens > target_tokens + answer_prefix_tokens: # Check against effective limit
            logger.warning(f"Final prompt ({final_prompt_tokens} tokens) exceeded effective target ({target_tokens + answer_prefix_tokens} tokens) despite budgeting. Formatting estimate might be too low.")
            # Consider truncating further if this happens often

        # 7. Send to LLM
        logger.debug("Sending final prompt to LLM...")
        try:
            llm_response = self.llm.generate(prompt=final_prompt)
            logger.info("Received response from LLM.")
            logger.debug(f"LLM Response (first 100 chars): {llm_response[:100]}...")
            # Return the response AND only the chunks ACTUALLY used
            return llm_response, selected_chunks 
        except Exception as e:
            logger.error(f"Error generating LLM response: {e}", exc_info=True)
            llm_response = "I encountered an error while trying to generate an answer."
            # Return error message and the chunks selected before the error
            return llm_response, selected_chunks 