"""API Endpoints for the HTMX Chat UI.
"""

import logging
import sqlite3
import uuid
from datetime import datetime, timezone
from typing import List, Dict, Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from fastapi.concurrency import run_in_threadpool # For sync retriever/generator methods

from transcript_engine.core.dependencies import (
    get_db,
    get_retriever, # Assuming this provides SimilarityRetriever
    get_generator, # Assuming this provides RAGService or similar generator
    get_templates,
)
from transcript_engine.database import crud
from transcript_engine.database.models import ChatMessage
from transcript_engine.interfaces.llm_interface import LLMInterface # For RAGService type hint if separate
from transcript_engine.query.retriever import SimilarityRetriever
from transcript_engine.query.rag_service import RAGService # Assuming this is the generator

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    tags=["Chat UI"],
    responses={404: {"description": "Not found"}},
)

@router.get("/", response_class=HTMLResponse)
async def get_chat_page(
    request: Request,
    templates: Jinja2Templates = Depends(get_templates)
):
    """Serves the main chat HTML page.
    
    Generates a new session ID for each page load initially.
    """
    session_id = str(uuid.uuid4())
    logger.info(f"Serving chat page, new session ID: {session_id}")
    # In a real app, load history based on session_id from cookie/db
    return templates.TemplateResponse(
        "chat.html", 
        {"request": request, "session_id": session_id, "chat_history": []}
    )

@router.post("/ask", response_class=HTMLResponse)
async def ask_question(
    request: Request, # Need request for TemplateResponse
    db: sqlite3.Connection = Depends(get_db),
    retriever: SimilarityRetriever = Depends(get_retriever),
    generator: RAGService = Depends(get_generator), # Use RAGService type
    templates: Jinja2Templates = Depends(get_templates),
    query_text: str = Form(...),
    session_id: str = Form(...),
    k_chunks: int = Form(5) # Make k configurable, default 5
):
    """Handles a user query submitted via HTMX form.
    
    Retrieves context, generates response, saves messages, and returns
    an HTML fragment containing the assistant's response.
    """
    logger.info(f"Received query for session {session_id}: '{query_text[:50]}...' (k={k_chunks})")

    try:
        # 1. Load History (Optional for context, but good practice)
        # chat_history_models = crud.get_chat_history(db, session_id)
        # Use RAGService's answer_question which handles retrieval + generation
        
        # 2. & 3. Retrieve and Generate using RAGService
        # Assuming RAGService.answer_question is sync, run in threadpool
        # If it's async, just await it.
        answer_text = await run_in_threadpool(
             generator.answer_question, query_text=query_text, k=k_chunks
        )
        # TODO: Get used_chunks back from RAGService if needed for tracebacks
        # For now, tracebacks will be empty
        tracebacks = []
        logger.debug(f"Generated answer for session {session_id}: '{answer_text[:100]}...'")

        # 4. Save Messages
        user_message = ChatMessage(
            session_id=session_id,
            role="user",
            content=query_text,
            # timestamp=datetime.now(timezone.utc) # Timestamp added by DB default
        )
        # Pass db, session_id, and the message object
        crud.add_chat_message(db, session_id, user_message)
        
        assistant_message = ChatMessage(
            # session_id=session_id, # Not needed in model if passed to function
            role="assistant",
            content=answer_text,
            # timestamp=datetime.now(timezone.utc) # Timestamp added by DB default
            # TODO: Add traceback info if available
        )
        # Pass db, session_id, and the message object
        crud.add_chat_message(db, session_id, assistant_message)
        
        # 5. Return HTML Fragment for HTMX
        return templates.TemplateResponse(
            "_chat_message.html",
            {
                "request": request, 
                "role": "assistant", 
                "content": answer_text, 
                "tracebacks": tracebacks
            }
        )

    except Exception as e:
        logger.error(f"Error processing /chat/ask for session {session_id}: {e}", exc_info=True)
        # Return an error message snippet via HTMX
        # You might want a specific error template fragment
        error_content = f"<div class='message error'>Sorry, an error occurred: {e}</div>"
        return HTMLResponse(content=error_content, status_code=500) 