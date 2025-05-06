"""Integration tests for the Actionable Items API endpoints."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch, MagicMock
from datetime import date, datetime, timedelta
import unittest.mock

# Assuming your FastAPI app instance is named 'app' in 'transcript_engine.main'
# Adjust the import according to your project structure if different.
from transcript_engine.main import app 
from transcript_engine.features.actionables_models import CandidateActionableItem

client = TestClient(app)

@pytest.fixture
def mock_get_transcript_for_timeframe_util():
    with patch('transcript_engine.api.routers.actionables.get_transcript_for_timeframe') as mock_util:
        yield mock_util

@pytest.fixture
def mock_scan_transcript_for_actionables_service():
    with patch('transcript_engine.api.routers.actionables.scan_transcript_for_actionables') as mock_service:
        yield mock_service

@pytest.fixture
def mock_extract_structured_data_service():
    with patch('transcript_engine.api.routers.actionables.extract_structured_data_for_item') as mock_service:
        yield mock_service

def test_scan_actionables_endpoint_success(mock_get_transcript_for_timeframe_util, mock_scan_transcript_for_actionables_service):
    target_date_str = "2023-10-27"
    timeframe = "morning"

    mock_get_transcript_for_timeframe_util.return_value = "Sample transcript segment for morning."
    mock_scan_transcript_for_actionables_service.return_value = [
        CandidateActionableItem(snippet="Call John", suggested_category="REMINDER", raw_entities="John"),
        CandidateActionableItem(snippet="Schedule meeting", suggested_category="EVENT", raw_entities="next week")
    ]

    response = client.post(
        "/api/v1/actionables/scan",
        json={"date": target_date_str, "timeframe": timeframe}
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["candidates"]) == 2
    assert data["candidates"][0]["snippet"] == "Call John"
    assert data["candidates"][0]["suggested_category"] == "REMINDER"
    assert data["candidates"][1]["snippet"] == "Schedule meeting"
    assert data["candidates"][1]["suggested_category"] == "EVENT"

    mock_get_transcript_for_timeframe_util.assert_called_once_with(
        db=unittest.mock.ANY, # Assuming db is correctly injected
        target_date=date(2023, 10, 27),
        timeframe_key=timeframe
    )
    mock_scan_transcript_for_actionables_service.assert_called_once_with(
        transcript_segment="Sample transcript segment for morning.",
        llm_service=unittest.mock.ANY, # Assuming llm_service is correctly injected
        target_date=date(2023, 10, 27),
        timeframe_key=timeframe
    )

def test_scan_actionables_endpoint_no_transcript_content(mock_get_transcript_for_timeframe_util, mock_scan_transcript_for_actionables_service):
    target_date_str = "2023-10-28"
    timeframe = "afternoon"

    mock_get_transcript_for_timeframe_util.return_value = "" # Empty string, no content

    response = client.post(
        "/api/v1/actionables/scan",
        json={"date": target_date_str, "timeframe": timeframe}
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["candidates"]) == 0
    mock_scan_transcript_for_actionables_service.assert_not_called() # Service should not be called if no segment

def test_scan_actionables_endpoint_no_candidates_found(mock_get_transcript_for_timeframe_util, mock_scan_transcript_for_actionables_service):
    target_date_str = "2023-10-29"
    timeframe = "evening"

    mock_get_transcript_for_timeframe_util.return_value = "Some content available."
    mock_scan_transcript_for_actionables_service.return_value = [] # LLM found no candidates

    response = client.post(
        "/api/v1/actionables/scan",
        json={"date": target_date_str, "timeframe": timeframe}
    )

    assert response.status_code == 200
    data = response.json()
    assert len(data["candidates"]) == 0

def test_scan_actionables_endpoint_invalid_date_format():
    response = client.post(
        "/api/v1/actionables/scan",
        json={"date": "not-a-date", "timeframe": "morning"}
    )
    assert response.status_code == 422 # Unprocessable Entity for Pydantic validation error

def test_scan_actionables_endpoint_future_date():
    future_d = (date.today() + timedelta(days=1)).strftime("%Y-%m-%d")
    response = client.post(
        "/api/v1/actionables/scan",
        json={"date": future_d, "timeframe": "morning"}
    )
    assert response.status_code == 422 # Pydantic validation error from ScanRequest model

def test_scan_actionables_endpoint_invalid_timeframe():
    response = client.post(
        "/api/v1/actionables/scan",
        json={"date": "2023-10-27", "timeframe": "brunch"}
    )
    assert response.status_code == 422 # Unprocessable Entity for Enum validation

def test_scan_actionables_endpoint_get_transcript_returns_none(mock_get_transcript_for_timeframe_util):
    target_date_str = "2023-11-01"
    timeframe = "morning"

    mock_get_transcript_for_timeframe_util.return_value = None # Simulate error from util (e.g. invalid key if not caught by Enum)

    response = client.post(
        "/api/v1/actionables/scan",
        json={"date": target_date_str, "timeframe": timeframe}
    )
    assert response.status_code == 500
    assert "Error retrieving transcript data" in response.json()["detail"]

def test_extract_structured_endpoint_success(mock_extract_structured_data_service):
    target_d_str = "2024-07-18"
    payload = {
        "confirmed_items": [
            {
                "user_snippet": "Meeting tomorrow 10am with team for project alpha",
                "final_category": "EVENT",
                "target_date": target_d_str
            },
            {
                "user_snippet": "Buy groceries this evening",
                "final_category": "TASK",
                "target_date": target_d_str
            }
        ]
    }

    # Mock return values for each call to the service
    mock_extract_structured_data_service.side_effect = [
        {"title": "Project Alpha Meeting", "start_datetime": "2024-07-19T10:00:00"}, # For first item
        {"title": "Buy groceries", "due_date": "2024-07-18"} # For second item
    ]

    response = client.post("/api/v1/actionables/extract_structured", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["processed_items"]) == 2
    
    assert data["processed_items"][0]["type"] == "EVENT"
    assert data["processed_items"][0]["details"]["title"] == "Project Alpha Meeting"
    assert data["processed_items"][0]["user_snippet"] == "Meeting tomorrow 10am with team for project alpha"
    assert data["processed_items"][0]["error_message"] is None

    assert data["processed_items"][1]["type"] == "TASK"
    assert data["processed_items"][1]["details"]["title"] == "Buy groceries"
    assert data["processed_items"][1]["user_snippet"] == "Buy groceries this evening"
    assert data["processed_items"][1]["error_message"] is None

    assert mock_extract_structured_data_service.call_count == 2
    # Check calls (order matters due to side_effect list)
    first_call_args = mock_extract_structured_data_service.call_args_list[0][1] # kwargs of first call
    assert first_call_args['item_snippet'] == "Meeting tomorrow 10am with team for project alpha"
    assert first_call_args['item_category'] == "EVENT"
    assert first_call_args['target_date'] == date(2024, 7, 18)

    second_call_args = mock_extract_structured_data_service.call_args_list[1][1]
    assert second_call_args['item_snippet'] == "Buy groceries this evening"
    assert second_call_args['item_category'] == "TASK"
    assert second_call_args['target_date'] == date(2024, 7, 18)

def test_extract_structured_endpoint_partial_failure(mock_extract_structured_data_service):
    target_d_str = "2024-07-18"
    payload = {
        "confirmed_items": [
            {
                "user_snippet": "Good item",
                "final_category": "EVENT",
                "target_date": target_d_str
            },
            {
                "user_snippet": "Bad item causes extraction failure",
                "final_category": "TASK",
                "target_date": target_d_str
            }
        ]
    }
    mock_extract_structured_data_service.side_effect = [
        {"title": "Good Event", "start_datetime": "2024-07-19T10:00:00"}, # Success
        None  # Failure for the second item
    ]

    response = client.post("/api/v1/actionables/extract_structured", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["processed_items"]) == 2

    assert data["processed_items"][0]["type"] == "EVENT"
    assert data["processed_items"][0]["details"] is not None
    assert data["processed_items"][0]["error_message"] is None

    assert data["processed_items"][1]["type"] == "TASK"
    assert data["processed_items"][1]["details"] is None
    assert data["processed_items"][1]["error_message"] is not None
    assert "Could not extract structured details" in data["processed_items"][1]["error_message"]

def test_extract_structured_endpoint_empty_input(mock_extract_structured_data_service):
    payload = {"confirmed_items": []}
    response = client.post("/api/v1/actionables/extract_structured", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert len(data["processed_items"]) == 0
    mock_extract_structured_data_service.assert_not_called()

def test_extract_structured_endpoint_service_unexpected_exception(mock_extract_structured_data_service):
    target_d_str = "2024-07-18"
    payload = {
        "confirmed_items": [
            {
                "user_snippet": "Item that will cause unexpected service error",
                "final_category": "REMINDER",
                "target_date": target_d_str
            }
        ]
    }
    mock_extract_structured_data_service.side_effect = Exception("Unexpected service layer boom!")

    response = client.post("/api/v1/actionables/extract_structured", json=payload)
    assert response.status_code == 200 # The endpoint itself handles item-level errors gracefully
    data = response.json()
    assert len(data["processed_items"]) == 1
    assert data["processed_items"][0]["type"] == "REMINDER"
    assert data["processed_items"][0]["details"] is None
    assert "An unexpected server error occurred" in data["processed_items"][0]["error_message"]
    assert "Unexpected service layer boom!" in data["processed_items"][0]["error_message"]

# It might also be useful to test for db errors if you can reliably mock the db connection
# at the endpoint level, or if get_transcript_for_timeframe itself raises a specific db error
# that translates to a 500, but the current setup with `Depends` makes this more complex
# for pure API integration tests without deeper service mocking or test DB setup. 