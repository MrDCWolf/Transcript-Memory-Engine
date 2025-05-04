"""API Endpoints for chat and RAG queries.
"""

import logging
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.concurrency import run_in_threadpool

from transcript_engine.query.rag_service import RAGService
from transcript_engine.core.dependencies import get_rag_service
from transcript_engine.api.models import QueryRequest, QueryResponse

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/chat",
    tags=["Chat / RAG"],
    responses={500: {"description": "Internal Server Error"}}, 
)

@router.post(
    "/query", 
    response_model=QueryResponse,
    summary="Query transcripts using RAG",
    description="Send a query to the Retrieval-Augmented Generation pipeline to get an answer based on ingested transcripts."
)
async def rag_query(
    request: QueryRequest,
    rag_service: RAGService = Depends(get_rag_service)
) -> QueryResponse:
    """Endpoint to perform a RAG query.

    Args:
        request: The query request containing the question and k value.
        rag_service: The injected RAGService instance.

    Returns:
        The generated answer.
    """
    try:
        logger.info(f"Received RAG query request: '{request.query_text[:100]}...', k={request.k}")
        # Run potentially blocking RAG logic in threadpool
        answer = await run_in_threadpool(
            rag_service.answer_question, query_text=request.query_text, k=request.k
        )
        logger.info(f"Returning RAG answer: '{answer[:100]}...'")
        return QueryResponse(answer=answer)
    except Exception as e:
        # Catch unexpected errors from the RAG service
        logger.error(f"Unexpected error during RAG query processing: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An unexpected error occurred while processing your query."
        ) 