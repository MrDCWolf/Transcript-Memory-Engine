"""Service implementing the Retrieval-Augmented Generation (RAG) pipeline.
"""

import logging
from typing import List, Dict, Any, Tuple
import sqlite3 # Import sqlite3 for the connection
from datetime import datetime, timezone
import tiktoken # Import tiktoken

from transcript_engine.query.retriever import SimilarityRetriever, TODAY_REGEX
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
- **Include Specific Details & Quotes:** Incorporate specific details, examples, and 1-2 concise, impactful quotes from the transcripts to support your points. Cite the source conversation/transcript ID if available, but prioritize flow over excessive citation.
- **Base Answer *Solely* on Provided Text:** Do *not* use any external knowledge. Your entire answer must be derived from the 'Chat History' and 'Transcript Excerpts' provided below.
- **Handle Missing Information:** If the answer cannot be synthesized from the provided text, state that clearly (e.g., "Based on the provided transcripts, I don't have enough information to answer that specific point."). Do not speculate.
- **Address Recency Queries:** If asked about the "latest" or "last" information (e.g., "last thing said today"), examine the provided Transcript Excerpts. Identify the excerpt that seems most recent based on its content or any associated metadata (like Transcript ID, if numerical IDs generally increase over time). State what that excerpt says, mentioning it appears to be the most recent *within the provided context*. Avoid definitive statements about it being the absolute last thing said if the context is limited.
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

    def answer_question(self, query_text: str, db_conn: sqlite3.Connection, k: int = 50) -> Tuple[str, List[Dict[str, Any]]]:
        """Answers a user question using RAG, dynamically managing context window.

        Args:
            query_text: The user's question.
            db_conn: An active sqlite3 database connection.
            k: The *initial* number of chunks to retrieve for potential inclusion.

        Returns:
            A tuple containing:
                - The LLM-generated answer string.
                - The list of chunk dictionaries *actually included* in the LLM prompt context.
        """
        logger.info(f"Processing query: '{query_text[:100]}...' (Retrieving initial k={k})")
        settings = get_settings()

        # --- Date Query Logic (remains the same, but uses passed db_conn) --- 
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
                # Use the passed db_conn directly
                # from transcript_engine.core.dependencies import get_db # No longer needed
                # db_conn = get_db() # No longer needed
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
        # Pass db_conn to retrieve method for potential filtering
        retrieved_chunks: List[Dict[str, Any]] = self.retriever.retrieve(
            query_text=query_text, 
            k=k,
            db_conn=db_conn # Pass the connection here
        )
        
        if not retrieved_chunks:
            logger.warning("No chunks retrieved for query. Cannot generate context-based answer.")
            return "I couldn't find any relevant information in the transcripts to answer your question.", []

        # Store retrieved chunks (potentially modify later)
        retrieved_chunk_data = retrieved_chunks
        retrieved_chunk_ids = {c.get('id') for c in retrieved_chunk_data if c.get('id')} # Use the chunk ID generated by ChromaStore

        # --- Explicitly fetch latest chunks if 'today' query ---
        is_today_query = bool(TODAY_REGEX.search(query_text))
        if is_today_query:
            logger.debug("'today' query detected. Attempting to fetch chunks from absolute latest transcript.")
            latest_transcript_id = crud.get_latest_transcript_id_for_today(db_conn)
            
            if latest_transcript_id:
                logger.debug(f"Latest transcript ID for today: {latest_transcript_id}. Fetching its chunks.")
                # Fetch the actual Chunk objects using the new CRUD function
                latest_transcript_chunks: List[Chunk] = crud.get_chunks_by_transcript_id(db_conn, latest_transcript_id)
                
                # Convert Chunk objects to the dictionary format used by RAG/ChromaStore
                # Also fetch the parent transcript's start time for sorting metadata
                parent_transcript = crud.get_transcript_by_id(db_conn, latest_transcript_id)
                parent_start_time_iso = parent_transcript.start_time.isoformat() if parent_transcript and parent_transcript.start_time else None
                
                explicitly_fetched_chunk_data = []
                for chunk_obj in latest_transcript_chunks:
                    # Generate the same ID format ChromaStore uses ({transcript_id}_{index}) 
                    # We need the index; fetching all chunks ensures we have it implicitly via list order
                    # Find the index of this chunk_obj in the full list (less efficient but works for now)
                    try:
                         chunk_index = latest_transcript_chunks.index(chunk_obj)
                         chroma_id = f"{latest_transcript_id}_{chunk_index}"
                    except ValueError:
                         chroma_id = f"{latest_transcript_id}_unknownidx" # Fallback ID
                         
                    # Check if this chunk (by generated ID) was already retrieved by semantic search
                    if chroma_id not in retrieved_chunk_ids:
                        metadata = {
                            "transcript_id": chunk_obj.transcript_id,
                            "start_time": chunk_obj.start_time, # Chunk start time if available
                            "end_time": chunk_obj.end_time, # Chunk end time if available
                            "transcript_start_time_iso": parent_start_time_iso # Add parent start time
                        }
                        chunk_dict = {
                            "id": chroma_id,
                            "content": chunk_obj.content,
                            "metadata": {k: v for k, v in metadata.items() if v is not None}
                            # Embedding is missing here, but we sort before budgeting, 
                            # so it might not be strictly necessary for the explicitly added chunk 
                            # unless relevance ranking within combined list is critical post-sort.
                            # For now, we omit it as we primarily want it for chronological position.
                        }
                        explicitly_fetched_chunk_data.append(chunk_dict)
                        retrieved_chunk_ids.add(chroma_id) # Add to set to track it
                        
                if explicitly_fetched_chunk_data:
                     logger.debug(f"Adding {len(explicitly_fetched_chunk_data)} chunks from latest transcript (ID: {latest_transcript_id}) to the retrieved set.")
                     retrieved_chunk_data.extend(explicitly_fetched_chunk_data)
            else:
                 logger.warning("Could not determine the latest transcript ID for today to explicitly fetch chunks.")

        # --- Sort combined chunks by Recency if 'today' query ---
        # This sorting now happens *after* potentially adding latest chunks
        if is_today_query:
             logger.debug("Sorting combined chunks by transcript start time (descending).")
             try:
                 # Sort in place, most recent first. Handle potential None or invalid times gracefully.
                 retrieved_chunk_data.sort(
                     key=lambda c: datetime.fromisoformat(c.get('metadata', {}).get('transcript_start_time_iso')) 
                                   if c.get('metadata', {}).get('transcript_start_time_iso') 
                                   else datetime.min.replace(tzinfo=timezone.utc), 
                     reverse=True
                 )
                 # Log the first few chunk times after sorting
                 if retrieved_chunk_data:
                     first_times = [
                         c.get('metadata', {}).get('transcript_start_time_iso')
                         for c in retrieved_chunk_data[:3]
                     ]
                     logger.debug(f"Top chunks after sorting by time (latest first): {first_times}")
             except Exception as e:
                 logger.warning(f"Could not sort combined chunks by timestamp due to error: {e}. Proceeding with original order.", exc_info=True)
        # ---------------------------------------

        # --- Add Transcript Start Time to Metadata --- 
        # (This block might be slightly redundant now as we added transcript_start_time_iso 
        # during the explicit fetch, but keeping it ensures chunks from semantic search also get it)
        try:
            # Use the passed db_conn
            # from transcript_engine.core.dependencies import get_db # No longer needed
            # db_conn = get_db() # No longer needed
            for chunk_dict in retrieved_chunk_data:
                 metadata = chunk_dict.setdefault('metadata', {}) # Ensure metadata exists
                 transcript_id = metadata.get('transcript_id')
                 if isinstance(transcript_id, int):
                      transcript = crud.get_transcript_by_id(db_conn, transcript_id) # Use passed db_conn
                      if transcript and transcript.start_time:
                           metadata['transcript_start_time_iso'] = transcript.start_time.isoformat()
                      else:
                           logger.warning(f"Could not find transcript or start_time for ID {transcript_id} referenced by a chunk.")
                 elif transcript_id:
                      logger.warning(f"Transcript ID '{transcript_id}' in chunk metadata is not an integer.")
        except Exception as e:
             logger.error(f"Error retrieving transcript start times for chunks: {e}", exc_info=True)
             # Continue without transcript start times if lookup fails
        # -------------------------------------------

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
        for i, chunk_dict in enumerate(retrieved_chunk_data):
            metadata = chunk_dict.get('metadata', {}) 
            content = chunk_dict.get('content', '')
            transcript_id = metadata.get('transcript_id', 'N/A')

            # Format chunk text as it will appear in the prompt for token calculation
            chunk_prefix = f"*{i+1}. (Transcript ID: {transcript_id}):*\n"
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

        # --- Log selected chunks if it was a 'today' query ---
        if is_today_query:
             selected_chunk_info = [
                 f"ID: {c.get('id', 'N/A')}, T_ID: {c.get('metadata', {}).get('transcript_id', 'N/A')}, Start: {c.get('metadata', {}).get('transcript_start_time_iso', 'N/A')[:19]}"
                 for c in selected_chunks
             ]
             logger.debug(f"Chunks selected for final context (after budget/sort): {selected_chunk_info}")
        # -----------------------------------------------------

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
                # REMOVED: Don't include time formatting in the LLM context
                # start_time = metadata.get('start_time', 'N/A') 
                # formatted_start_time = start_time # Reformat again for final prompt
                # if isinstance(start_time, (int, float)):
                #     try:
                #         dt_obj = datetime.fromtimestamp(start_time, tz=timezone.utc)
                #         formatted_start_time = dt_obj.strftime("%Y-%m-%d %H:%M:%S UTC")
                #     except (ValueError, TypeError): formatted_start_time = "Invalid Timestamp"
                # elif not isinstance(start_time, str): formatted_start_time = str(start_time)

                # Include only Transcript ID in the prefix for the LLM
                context_str_parts.append(f"*{i+1}. (Transcript ID: {transcript_id}):*\n{content}")
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

        # --- Log final prompt for debugging 'today' queries ---
        if is_today_query:
             logger.debug(f"Final prompt being sent to LLM:\n------\n{final_prompt}\n------")
        # -----------------------------------------------------

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