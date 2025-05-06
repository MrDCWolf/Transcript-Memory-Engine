"""Pydantic models for the Actionable Items feature."""

from pydantic import BaseModel
from typing import Optional, List

class CandidateActionableItem(BaseModel):
    """Represents a candidate actionable item identified by the local LLM."""
    snippet: str
    suggested_category: str # E.g., "REMINDER", "EVENT", "TASK"
    raw_entities: Optional[str] = None # Raw text of any identified entities

# --- Schemas for Structured Data Extraction (for Google Services) ---

class GoogleCalendarEventSchema(BaseModel):
    title: str
    start_datetime: str # ISO 8601 format, e.g., "2024-07-15T09:00:00Z" or "2024-07-15T09:00:00-07:00"
    end_datetime: Optional[str] = None # ISO 8601 format
    description: Optional[str] = None
    location: Optional[str] = None
    attendees: Optional[List[str]] = None # List of email addresses

class GoogleTaskSchema(BaseModel):
    title: str
    due_date: Optional[str] = None # ISO 8601 date format, e.g., "2024-07-15"
    notes: Optional[str] = None

class GoogleReminderSchema(BaseModel):
    """Schema for Google Reminders.
    Note: Direct Google Reminders API is limited. This might be adapted 
    to use Google Tasks API with a due date/time for similar functionality.
    """
    title: str
    remind_at_datetime: str # ISO 8601 format, e.g., "2024-07-15T09:00:00Z" 