"""Unit tests for Google API service functions."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import datetime

from google.oauth2.credentials import Credentials
from googleapiclient.errors import HttpError

from transcript_engine.features.google_services import add_to_google_calendar, add_to_google_tasks
from transcript_engine.features.actionables_models import GoogleCalendarEventSchema, GoogleTaskSchema

@pytest.fixture
def mock_google_credentials():
    """Fixture for mocked Google Credentials."""
    return MagicMock(spec=Credentials)

@pytest.fixture
def mock_google_build_service():
    """Fixture to mock googleapiclient.discovery.build."""
    with patch('transcript_engine.features.google_services.build') as mock_build:
        yield mock_build

# --- Tests for add_to_google_calendar ---
def test_add_to_google_calendar_success(mock_google_credentials, mock_google_build_service):
    event_details = GoogleCalendarEventSchema(
        title="Test Event",
        start_datetime="2024-08-01T10:00:00Z",
        end_datetime="2024-08-01T11:00:00Z",
        description="Event description",
        location="Event location",
        attendees=["test@example.com"]
    )
    mock_service_instance = MagicMock()
    mock_events_resource = MagicMock()
    mock_insert_method = MagicMock()
    mock_google_build_service.return_value = mock_service_instance
    mock_service_instance.events.return_value = mock_events_resource
    mock_events_resource.insert.return_value = mock_insert_method
    mock_insert_method.execute.return_value = {
        'id': 'calendar_event_id_123',
        'htmlLink': 'http://calendar.google.com/event_link'
    }

    result = add_to_google_calendar(mock_google_credentials, event_details)

    assert result == 'http://calendar.google.com/event_link'
    mock_google_build_service.assert_called_once_with('calendar', 'v3', credentials=mock_google_credentials)
    expected_body = {
        'summary': 'Test Event',
        'location': 'Event location',
        'description': 'Event description',
        'start': {'dateTime': '2024-08-01T10:00:00Z'},
        'end': {'dateTime': '2024-08-01T11:00:00Z'},
        'attendees': [{'email': 'test@example.com'}]
    }
    mock_events_resource.insert.assert_called_once_with(calendarId='primary', body=expected_body)
    mock_insert_method.execute.assert_called_once()

def test_add_to_google_calendar_minimal_data(mock_google_credentials, mock_google_build_service):
    event_details = GoogleCalendarEventSchema(
        title="Minimal Event",
        start_datetime="2024-08-01T14:00:00Z"
    )
    mock_service_instance = MagicMock()
    mock_events_resource = MagicMock()
    mock_insert_method = MagicMock()
    mock_google_build_service.return_value = mock_service_instance
    mock_service_instance.events.return_value = mock_events_resource
    mock_events_resource.insert.return_value = mock_insert_method
    mock_insert_method.execute.return_value = {
        'id': 'cal_event_min_456',
        'htmlLink': 'http://calendar.google.com/event_link_min'
    }

    result = add_to_google_calendar(mock_google_credentials, event_details)
    assert result == 'http://calendar.google.com/event_link_min'
    expected_body = {
        'summary': 'Minimal Event',
        'start': {'dateTime': '2024-08-01T14:00:00Z'}
        # No end, location, description, attendees as they are None
    }
    mock_events_resource.insert.assert_called_once_with(calendarId='primary', body=expected_body)

def test_add_to_google_calendar_http_error(mock_google_credentials, mock_google_build_service):
    event_details = GoogleCalendarEventSchema(title="Error Event", start_datetime="2024-01-01T00:00:00Z")
    mock_service_instance = MagicMock()
    mock_google_build_service.return_value = mock_service_instance
    # Simulate HttpError from googleapiclient
    # The actual HttpError needs a response object and content.
    mock_resp = MagicMock()
    mock_resp.status = 400
    mock_resp.reason = "Bad Request"
    mock_service_instance.events().insert().execute.side_effect = HttpError(resp=mock_resp, content=b'error content')

    result = add_to_google_calendar(mock_google_credentials, event_details)
    assert result is None

# --- Tests for add_to_google_tasks ---
def test_add_to_google_tasks_success(mock_google_credentials, mock_google_build_service):
    task_details = GoogleTaskSchema(
        title="Test Task",
        notes="Task notes",
        due_date="2024-08-05" # YYYY-MM-DD
    )
    mock_service_instance = MagicMock()
    mock_tasks_resource = MagicMock()
    mock_insert_method = MagicMock()
    mock_google_build_service.return_value = mock_service_instance
    mock_service_instance.tasks.return_value = mock_tasks_resource
    mock_tasks_resource.insert.return_value = mock_insert_method
    mock_insert_method.execute.return_value = {
        'id': 'task_id_789',
        'title': 'Test Task'
    }

    result = add_to_google_tasks(mock_google_credentials, task_details)
    assert result == 'task_id_789'
    mock_google_build_service.assert_called_once_with('tasks', 'v1', credentials=mock_google_credentials)
    expected_body = {
        'title': 'Test Task',
        'notes': 'Task notes',
        'due': '2024-08-05T00:00:00Z' # Function should format this
    }
    mock_tasks_resource.insert.assert_called_once_with(tasklist='@default', body=expected_body)
    mock_insert_method.execute.assert_called_once()

def test_add_to_google_tasks_no_due_date_or_notes(mock_google_credentials, mock_google_build_service):
    task_details = GoogleTaskSchema(title="Simple Task")
    mock_service_instance = MagicMock()
    mock_tasks_resource = MagicMock()
    mock_insert_method = MagicMock()
    mock_google_build_service.return_value = mock_service_instance
    mock_service_instance.tasks.return_value = mock_tasks_resource
    mock_tasks_resource.insert.return_value = mock_insert_method
    mock_insert_method.execute.return_value = {'id': 'task_simple_123', 'title': 'Simple Task'}

    result = add_to_google_tasks(mock_google_credentials, task_details)
    assert result == 'task_simple_123'
    expected_body = {'title': 'Simple Task'}
    mock_tasks_resource.insert.assert_called_once_with(tasklist='@default', body=expected_body)

def test_add_to_google_tasks_due_date_already_datetime_str(mock_google_credentials, mock_google_build_service):
    full_datetime_str = "2024-08-10T15:30:00Z"
    task_details = GoogleTaskSchema(title="Task with Full DueTime", due_date=full_datetime_str)
    mock_service_instance = MagicMock()
    mock_google_build_service.return_value = mock_service_instance
    mock_service_instance.tasks().insert().execute.return_value = {'id': 'task_dt_456'}
    
    add_to_google_tasks(mock_google_credentials, task_details)
    expected_body = {'title': 'Task with Full DueTime', 'due': full_datetime_str}
    mock_service_instance.tasks().insert.assert_called_once_with(tasklist='@default', body=expected_body)

def test_add_to_google_tasks_http_error(mock_google_credentials, mock_google_build_service):
    task_details = GoogleTaskSchema(title="Error Task")
    mock_service_instance = MagicMock()
    mock_google_build_service.return_value = mock_service_instance
    mock_resp = MagicMock()
    mock_resp.status = 500
    mock_resp.reason = "Server Error"
    mock_service_instance.tasks().insert().execute.side_effect = HttpError(resp=mock_resp, content=b'server error content')

    result = add_to_google_tasks(mock_google_credentials, task_details)
    assert result is None 