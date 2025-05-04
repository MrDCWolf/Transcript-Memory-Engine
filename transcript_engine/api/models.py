"""Pydantic models for API request and response bodies.
"""

from pydantic import BaseModel, Field

class QueryRequest(BaseModel):
    """Request model for submitting a query to the RAG service.
    """
    query_text: str = Field(..., description="The user's question.")
    k: int = Field(5, description="Number of chunks to retrieve for context.", gt=0)

class QueryResponse(BaseModel):
    """Response model for the RAG service's answer.
    """
    answer: str = Field(..., description="The generated answer based on retrieved context.") 