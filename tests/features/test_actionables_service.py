"""Unit tests for the actionable items service."""

import pytest
from unittest.mock import MagicMock, patch
from datetime import date
import json

from transcript_engine.features.actionables_service import scan_transcript_for_actionables, extract_structured_data_for_item
from transcript_engine.features.actionables_models import CandidateActionableItem
from transcript_engine.interfaces.llm_interface import LLMInterface
from transcript_engine.core.config import Settings
from openai import OpenAI

@pytest.fixture
def mock_llm_service():
    """Fixture for a mocked LLMInterface."""
    return MagicMock(spec=LLMInterface)

@pytest.fixture
def mock_openai_client():
    with patch('transcript_engine.features.actionables_service.OpenAI') as mock_client_constructor:
        mock_instance = MagicMock(spec=OpenAI)
        mock_client_constructor.return_value = mock_instance
        yield mock_instance

@pytest.fixture
def mock_settings_openai(monkeypatch):
    settings = Settings() # Load actual settings to modify
    settings.OPENAI_API_KEY = "fake_api_key"
    settings.OPENAI_CHAT_MODEL_NAME = "gpt-test"
    
    # Use monkeypatch to replace get_settings in the service module
    monkeypatch.setattr('transcript_engine.features.actionables_service.get_settings', lambda: settings)
    return settings

class MockToolCallFunction:
    def __init__(self, name, arguments_json_string):
        self.name = name
        self.arguments = arguments_json_string

class MockToolCall:
    def __init__(self, function_name, arguments_json_string):
        self.function = MockToolCallFunction(function_name, arguments_json_string)

class MockMessage:
    def __init__(self, tool_calls=None):
        self.tool_calls = tool_calls if tool_calls else []

class MockChoice:
    def __init__(self, message):
        self.message = message

class MockChatCompletion:
    def __init__(self, choices):
        self.choices = choices

def test_scan_transcript_for_actionables_success_single_item(mock_llm_service):
    transcript_segment = "User A: Remind me to call John tomorrow. User B: Okay."
    target_d = date(2023, 10, 27)
    timeframe_k = "morning"
    
    llm_response = """
- Snippet: Remind me to call John tomorrow.
  Category: REMINDER
  Entities: John, tomorrow
"""
    mock_llm_service.generate.return_value = llm_response

    result = scan_transcript_for_actionables(transcript_segment, mock_llm_service, target_d, timeframe_k)

    assert len(result) == 1
    assert result[0].snippet == "Remind me to call John tomorrow."
    assert result[0].suggested_category == "REMINDER"
    assert result[0].raw_entities == "john, tomorrow"
    mock_llm_service.generate.assert_called_once()

def test_scan_transcript_for_actionables_success_multiple_items(mock_llm_service):
    transcript_segment = "Lots of discussion here."
    target_d = date(2023, 10, 27)
    timeframe_k = "afternoon"

    llm_response = """
- Snippet: We need to schedule a meeting for next Monday.
  Category: EVENT
  Entities: next Monday
- Snippet: Add 'buy milk' to the shopping list.
  Category: TASK
  Entities: buy milk
- Snippet: Don't forget the dry cleaning.
  Category: REMINDER
  Entities: dry cleaning
"""
    mock_llm_service.generate.return_value = llm_response
    result = scan_transcript_for_actionables(transcript_segment, mock_llm_service, target_d, timeframe_k)

    assert len(result) == 3
    assert result[0].snippet == "We need to schedule a meeting for next Monday."
    assert result[0].suggested_category == "EVENT"
    assert result[0].raw_entities == "next monday"
    assert result[1].snippet == "Add 'buy milk' to the shopping list."
    assert result[1].suggested_category == "TASK"
    assert result[1].raw_entities == "buy milk"
    assert result[2].snippet == "Don't forget the dry cleaning."
    assert result[2].suggested_category == "REMINDER"
    assert result[2].raw_entities == "dry cleaning"

def test_scan_transcript_for_actionables_no_items_found_explicit(mock_llm_service):
    transcript_segment = "A quiet day."
    target_d = date(2023, 10, 27)
    timeframe_k = "evening"
    mock_llm_service.generate.return_value = "No actionable items found."

    result = scan_transcript_for_actionables(transcript_segment, mock_llm_service, target_d, timeframe_k)
    assert len(result) == 0

def test_scan_transcript_for_actionables_no_items_found_implicit(mock_llm_service):
    transcript_segment = "More quietness."
    target_d = date(2023, 10, 27)
    timeframe_k = "morning"
    mock_llm_service.generate.return_value = "Well, I looked and there is nothing here."
    # Relies on the parsing failing to find structured items, and final check
    result = scan_transcript_for_actionables(transcript_segment, mock_llm_service, target_d, timeframe_k)
    assert len(result) == 0

def test_scan_transcript_for_actionables_empty_transcript_segment(mock_llm_service):
    result = scan_transcript_for_actionables("", mock_llm_service, date(2023,1,1), "morning")
    assert len(result) == 0
    mock_llm_service.generate.assert_not_called()

    result_space = scan_transcript_for_actionables("   ", mock_llm_service, date(2023,1,1), "morning")
    assert len(result_space) == 0
    mock_llm_service.generate.assert_not_called()

def test_scan_transcript_for_actionables_llm_error(mock_llm_service):
    transcript_segment = "This will cause an error."
    target_d = date(2023, 10, 27)
    timeframe_k = "afternoon"
    mock_llm_service.generate.side_effect = Exception("LLM unavailable")

    result = scan_transcript_for_actionables(transcript_segment, mock_llm_service, target_d, timeframe_k)
    assert len(result) == 0

def test_scan_transcript_for_actionables_malformed_category(mock_llm_service):
    transcript_segment = "Test malformed category."
    target_d = date(2023, 10, 27)
    timeframe_k = "morning"
    llm_response = """
- Snippet: This is a task.
  Category: TAAASK
  Entities: something
- Snippet: This is an event.
  Category: EVENT
  Entities: an event
"""
    mock_llm_service.generate.return_value = llm_response
    result = scan_transcript_for_actionables(transcript_segment, mock_llm_service, target_d, timeframe_k)
    
    assert len(result) == 1 # Only the valid EVENT item should be parsed
    assert result[0].suggested_category == "EVENT"
    assert result[0].snippet == "This is an event."

def test_scan_transcript_for_actionables_missing_entities(mock_llm_service):
    transcript_segment = "Test missing entities."
    target_d = date(2023, 10, 27)
    timeframe_k = "evening"
    llm_response = """
- Snippet: Remind me about the thing.
  Category: REMINDER
"""
    mock_llm_service.generate.return_value = llm_response
    result = scan_transcript_for_actionables(transcript_segment, mock_llm_service, target_d, timeframe_k)

    assert len(result) == 1
    assert result[0].snippet == "Remind me about the thing."
    assert result[0].suggested_category == "REMINDER"
    assert result[0].raw_entities is None

def test_scan_transcript_for_actionables_multiline_snippet_and_entities(mock_llm_service):
    transcript_segment = "Complex discussion."
    target_d = date(2023, 10, 28)
    timeframe_k = "morning"
    llm_response = """
- Snippet: Let's plan the project kickoff.
  It should be next week.
  Category: EVENT
  Entities: project kickoff
  next week
- Snippet: My main task for today is:
  Finish the report.
  And also prepare slides.
  Category: TASK
  Entities: finish report
  prepare slides
"""
    mock_llm_service.generate.return_value = llm_response
    result = scan_transcript_for_actionables(transcript_segment, mock_llm_service, target_d, timeframe_k)

    assert len(result) == 2
    assert result[0].snippet == "Let's plan the project kickoff.\nIt should be next week."
    assert result[0].suggested_category == "EVENT"
    assert result[0].raw_entities == "project kickoff\nnext week"
    
    assert result[1].snippet == "My main task for today is:\nFinish the report.\nAnd also prepare slides."
    assert result[1].suggested_category == "TASK"
    assert result[1].raw_entities == "finish report\nprepare slides"

def test_scan_transcript_for_actionables_extra_whitespace_robustness(mock_llm_service):
    transcript_segment = "Test extra whitespace."
    target_d = date(2023,10,27)
    timeframe_k = "afternoon"
    llm_response = """
    -   Snippet:   Call Mom for her birthday.   
      Category:  REMINDER  
       Entities:   Mom, birthday   

- Snippet:Plan the team outing.
  Category:EVENT
  Entities: Team outing

"""
    mock_llm_service.generate.return_value = llm_response
    result = scan_transcript_for_actionables(transcript_segment, mock_llm_service, target_d, timeframe_k)

    assert len(result) == 2
    assert result[0].snippet == "Call Mom for her birthday."
    assert result[0].suggested_category == "REMINDER"
    assert result[0].raw_entities == "mom, birthday"

    assert result[1].snippet == "Plan the team outing."
    assert result[1].suggested_category == "EVENT"
    assert result[1].raw_entities == "team outing"

def test_scan_transcript_for_actionables_item_without_category(mock_llm_service):
    transcript_segment = "Testing item without category."
    target_d = date(2023, 10, 27)
    timeframe_k = "morning"
    llm_response = """
- Snippet: This is a test snippet.
  Entities: test entity
- Snippet: This is another test snippet with category.
  Category: TASK
  Entities: another test entity
"""
    mock_llm_service.generate.return_value = llm_response
    result = scan_transcript_for_actionables(transcript_segment, mock_llm_service, target_d, timeframe_k)

    assert len(result) == 1 # Should only parse the item with a category
    assert result[0].snippet == "This is another test snippet with category."
    assert result[0].suggested_category == "TASK"
    assert result[0].raw_entities == "another test entity"

def test_scan_transcript_for_actionables_item_block_with_only_snippet(mock_llm_service):
    transcript_segment = "Testing item block with only snippet."
    target_d = date(2023, 10, 27)
    timeframe_k = "evening"
    llm_response = """
- Snippet: Just a random thought, not really actionable.
- Snippet: Setup meeting with Marketing.
  Category: EVENT
  Entities: Marketing team, Meeting
"""
    mock_llm_service.generate.return_value = llm_response
    result = scan_transcript_for_actionables(transcript_segment, mock_llm_service, target_d, timeframe_k)
    assert len(result) == 1
    assert result[0].snippet == "Setup meeting with Marketing."
    assert result[0].suggested_category == "EVENT"

    assert len(result) == 1
    assert result[0].snippet == "Setup meeting with Marketing."
    assert result[0].suggested_category == "EVENT"

def test_extract_structured_data_event_success(mock_openai_client, mock_settings_openai):
    item_snippet = "Let's meet for coffee tomorrow at 9am at The Coffee Shop to discuss the project."
    item_category = "EVENT"
    target_d = date(2024, 7, 15) # Monday

    expected_function_name = "create_google_event"
    mock_args = {
        "title": "Coffee Meeting",
        "start_datetime": "2024-07-16T09:00:00",
        "location": "The Coffee Shop",
        "description": "Discuss the project"
    }
    mock_response = MockChatCompletion(
        choices=[MockChoice(message=MockMessage(
            tool_calls=[MockToolCall(function_name=expected_function_name, arguments_json_string=json.dumps(mock_args))]
        ))]
    )
    mock_openai_client.chat.completions.create.return_value = mock_response

    result = extract_structured_data_for_item(item_snippet, item_category, target_d)

    assert result is not None
    assert result["title"] == "Coffee Meeting"
    assert result["start_datetime"] == "2024-07-16T09:00:00"
    assert result["location"] == "The Coffee Shop"
    assert result["description"] == "Discuss the project"
    mock_openai_client.chat.completions.create.assert_called_once()

def test_extract_structured_data_task_success(mock_openai_client, mock_settings_openai):
    item_snippet = "I need to finish the report by Friday and also send the email update."
    item_category = "TASK"
    target_d = date(2024, 7, 15) # Monday

    expected_function_name = "create_google_task"
    mock_args = {
        "title": "Finish report and send email update",
        "due_date": "2024-07-19", # Friday
        "notes": "Report due by Friday. Also send email update."
    }
    mock_response = MockChatCompletion(
        choices=[MockChoice(message=MockMessage(
            tool_calls=[MockToolCall(function_name=expected_function_name, arguments_json_string=json.dumps(mock_args))]
        ))]
    )
    mock_openai_client.chat.completions.create.return_value = mock_response

    result = extract_structured_data_for_item(item_snippet, item_category, target_d)

    assert result is not None
    assert result["title"] == "Finish report and send email update"
    assert result["due_date"] == "2024-07-19"
    assert result["notes"] == "Report due by Friday. Also send email update."

def test_extract_structured_data_no_api_key(monkeypatch):
    settings_no_key = Settings()
    settings_no_key.OPENAI_API_KEY = None
    monkeypatch.setattr('transcript_engine.features.actionables_service.get_settings', lambda: settings_no_key)
    
    result = extract_structured_data_for_item("test snippet", "EVENT", date.today())
    assert result is None

def test_extract_structured_data_invalid_category(mock_settings_openai):
    result = extract_structured_data_for_item("test snippet", "INVALID_CATEGORY", date.today())
    assert result is None

def test_extract_structured_data_openai_api_error(mock_openai_client, mock_settings_openai):
    mock_openai_client.chat.completions.create.side_effect = Exception("OpenAI API Error")
    result = extract_structured_data_for_item("test snippet", "TASK", date.today())
    assert result is None

def test_extract_structured_data_no_tool_call_returned(mock_openai_client, mock_settings_openai):
    mock_response = MockChatCompletion(choices=[MockChoice(message=MockMessage(tool_calls=None))])
    mock_openai_client.chat.completions.create.return_value = mock_response
    result = extract_structured_data_for_item("test snippet", "EVENT", date.today())
    assert result is None

def test_extract_structured_data_wrong_function_name(mock_openai_client, mock_settings_openai):
    mock_args = {"title": "Test"}
    mock_response = MockChatCompletion(
        choices=[MockChoice(message=MockMessage(
            tool_calls=[MockToolCall(function_name="wrong_function", arguments_json_string=json.dumps(mock_args))]
        ))]
    )
    mock_openai_client.chat.completions.create.return_value = mock_response
    result = extract_structured_data_for_item("test snippet", "REMINDER", date.today())
    assert result is None

def test_extract_structured_data_json_decode_error(mock_openai_client, mock_settings_openai):
    expected_function_name = "create_google_task"
    mock_response = MockChatCompletion(
        choices=[MockChoice(message=MockMessage(
            tool_calls=[MockToolCall(function_name=expected_function_name, arguments_json_string="not valid json")]))]
    )
    mock_openai_client.chat.completions.create.return_value = mock_response
    result = extract_structured_data_for_item("test snippet", "TASK", date.today())
    assert result is None

def test_extract_structured_data_pydantic_validation_error(mock_openai_client, mock_settings_openai):
    expected_function_name = "create_google_event"
    # Missing required 'title' field for GoogleCalendarEventSchema
    mock_args = {"start_datetime": "2024-07-16T09:00:00"} 
    mock_response = MockChatCompletion(
        choices=[MockChoice(message=MockMessage(
            tool_calls=[MockToolCall(function_name=expected_function_name, arguments_json_string=json.dumps(mock_args))]))]
    )
    mock_openai_client.chat.completions.create.return_value = mock_response
    result = extract_structured_data_for_item("test snippet", "EVENT", date.today())
    assert result is None 