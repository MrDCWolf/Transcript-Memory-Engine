"""Service functions for interacting with Google Calendar and Google Tasks APIs."""

import logging
from typing import Optional, Dict, Any
from datetime import datetime

from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build, Resource
from googleapiclient.errors import HttpError

from transcript_engine.features.actionables_models import GoogleCalendarEventSchema, GoogleTaskSchema

logger = logging.getLogger(__name__)

def add_to_google_calendar(credentials: Credentials, event_details: GoogleCalendarEventSchema) -> Optional[str]:
    """Adds an event to the user's primary Google Calendar.

    Args:
        credentials: Authenticated Google OAuth2 credentials.
        event_details: A Pydantic model instance of GoogleCalendarEventSchema 
                       containing the event details.

    Returns:
        The HTML link to the created event, or None if creation failed.
    """
    try:
        service: Resource = build('calendar', 'v3', credentials=credentials)
        
        event_body = {
            'summary': event_details.title,
            'location': event_details.location,
            'description': event_details.description,
            'start': {
                'dateTime': event_details.start_datetime,
                # 'timeZone': 'America/Los_Angeles', # Optional: Consider user's timezone or UTC
            },
            'end': {
                'dateTime': event_details.end_datetime,
                # 'timeZone': 'America/Los_Angeles', # Optional
            },
            # 'recurrence': [
            #     'RRULE:FREQ=DAILY;COUNT=2'
            # ],
            'attendees': [{'email': email} for email in event_details.attendees] if event_details.attendees else [],
            # 'reminders': {
            #     'useDefault': False,
            #     'overrides': [
            #         {'method': 'email', 'minutes': 24 * 60},
            #         {'method': 'popup', 'minutes': 10},
            #     ],
            # },
        }
        # Filter out None values from event_body to avoid API errors for optional fields
        event_body_cleaned = {k: v for k, v in event_body.items() if v is not None}
        if 'start' in event_body_cleaned and event_body_cleaned['start'].get('dateTime') is None:
            del event_body_cleaned['start'] # Or handle as error if start time is mandatory
        if 'end' in event_body_cleaned and event_body_cleaned['end'].get('dateTime') is None:
            del event_body_cleaned['end']
        # Ensure start and end are present if their sub-fields were populated
        if event_details.start_datetime and 'start' not in event_body_cleaned:
             event_body_cleaned['start'] = {'dateTime': event_details.start_datetime}
        if event_details.end_datetime and 'end' not in event_body_cleaned:
             event_body_cleaned['end'] = {'dateTime': event_details.end_datetime}

        logger.debug(f"Attempting to create Google Calendar event: {event_body_cleaned}")
        
        created_event = service.events().insert(
            calendarId='primary', 
            body=event_body_cleaned
        ).execute()
        
        event_link = created_event.get('htmlLink')
        logger.info(f"Successfully created Google Calendar event. ID: {created_event['id']}, Link: {event_link}")
        return event_link

    except HttpError as error:
        logger.error(f"An HTTP error occurred while creating Google Calendar event: {error}", exc_info=True)
        # You could parse error.content for more specific messages
        # error_details = error.resp.reason or error._get_reason()
        # logger.error(f"Error details: {error_details}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while creating Google Calendar event: {e}", exc_info=True)
        return None

def add_to_google_tasks(credentials: Credentials, task_details: GoogleTaskSchema) -> Optional[str]:
    """Adds a task to the user's default Google Tasks list.

    Args:
        credentials: Authenticated Google OAuth2 credentials.
        task_details: A Pydantic model instance of GoogleTaskSchema 
                      containing the task details.

    Returns:
        The ID of the created task, or None if creation failed.
        (Google Tasks API v1 does not directly return an HTML link for a task,
         but returns the task resource which includes an ID).
    """
    try:
        service: Resource = build('tasks', 'v1', credentials=credentials)

        task_body = {
            'title': task_details.title,
            'notes': task_details.notes,
            # Due date should be in RFC3339 flotmat: "YYYY-MM-DDTHH:MM:SS.mmmZ"
            # GoogleTaskSchema currently has due_date as "YYYY-MM-DD"
            # The Tasks API expects a full dateTime for 'due'. 
            # If only date is provided, we might need to format it as T00:00:00Z or handle appropriately.
            # For simplicity, if due_date is just a date, we might need to adjust or the API might handle it.
            # Let's assume for now the API handles date-only strings for 'due' or it's already formatted correctly.
            # A common practice for date-only is to set time to midnight UTC.
            'due': None 
        }
        if task_details.due_date:
            try:
                # Attempt to parse as date and format as full RFC3339 datetime at midnight UTC
                # This assumes due_date from schema is YYYY-MM-DD
                due_dt = datetime.fromisoformat(task_details.due_date + "T00:00:00Z")
                task_body['due'] = due_dt.isoformat()
            except ValueError:
                logger.warning(f"Could not parse due_date '{task_details.due_date}' as YYYY-MM-DD. Sending as is or omitting.")
                # If it's already a full datetime string, the LLM might have provided it.
                # Or, if it's not parsable, it might be better to omit or handle error.
                # For now, let's try to pass it if it was already a full string, else omit if parse failed.
                if 'T' in task_details.due_date and 'Z' in task_details.due_date: # Basic check for datetime like string
                    task_body['due'] = task_details.due_date
                else:
                    del task_body['due'] # Remove if not a valid RFC3339 datetime

        task_body_cleaned = {k: v for k, v in task_body.items() if v is not None}

        logger.debug(f"Attempting to create Google Task: {task_body_cleaned}")

        # Insert the task into the default task list ('@default')
        created_task = service.tasks().insert(
            tasklist='@default', 
            body=task_body_cleaned
        ).execute()

        task_id = created_task.get('id')
        logger.info(f"Successfully created Google Task. ID: {task_id}")
        # The selfLink or an ID is usually returned. A direct web link is not standard in response.
        # Constructing a link might be possible if Google Tasks has a consistent URL pattern for tasks.
        # For now, returning ID is safest.
        return task_id 

    except HttpError as error:
        logger.error(f"An HTTP error occurred while creating Google Task: {error}", exc_info=True)
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred while creating Google Task: {e}", exc_info=True)
        return None

# TODO: Implement add_to_google_tasks 