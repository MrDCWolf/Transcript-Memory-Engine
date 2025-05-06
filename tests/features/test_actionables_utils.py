"""Unit tests for actionable items utility functions."""

import sqlite3
import pytest
from unittest.mock import MagicMock, patch
from datetime import date, datetime, timezone, timedelta

from transcript_engine.features.actionables_utils import get_transcript_for_timeframe
from transcript_engine.database.models import Transcript, Chunk
from transcript_engine.core.config import Settings

# Sample timeframe boundaries for testing
SAMPLE_TIMEFRAME_BOUNDARIES = {
    "morning": (6, 12),    # 6:00 AM to 11:59 AM
    "afternoon": (12, 18), # 12:00 PM to 5:59 PM
    "evening": (18, 24),   # 6:00 PM to 11:59 PM
    "full_day": (0, 24)
}

@pytest.fixture
def mock_db_connection():
    """Fixture for a mocked sqlite3.Connection."""
    return MagicMock(spec=sqlite3.Connection)

@pytest.fixture
def mock_settings():
    """Fixture for a mocked Settings object with sample timeframe boundaries."""
    settings = MagicMock(spec=Settings)
    settings.TIMEFRAME_BOUNDARIES = SAMPLE_TIMEFRAME_BOUNDARIES
    return settings

@patch('transcript_engine.features.actionables_utils.get_settings')
def test_get_transcript_for_timeframe_morning_chunks_found(mock_get_settings, mock_db_connection, mock_settings):
    mock_get_settings.return_value = mock_settings
    target_d = date(2023, 10, 26)

    # Transcript starts at 8:00 AM UTC on the target date
    transcript1_start_utc = datetime(2023, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    transcript1 = Transcript(
        id=1, source="test", source_id="t1", start_time=transcript1_start_utc, created_at=datetime.now(), updated_at=datetime.now(), is_chunked=True
    )
    # Chunks relative to transcript1_start_utc
    # Chunk 1: 8:00 AM + 0s = 8:00 AM (morning)
    # Chunk 2: 8:00 AM + 3600s (1hr) = 9:00 AM (morning)
    # Chunk 3: 8:00 AM + 14400s (4hr) = 12:00 PM (afternoon - boundary, should NOT be included in morning)
    chunks_t1 = [
        Chunk(id=10, transcript_id=1, content="Morning content 1", start_time=0, created_at=datetime.now(), updated_at=datetime.now()),
        Chunk(id=11, transcript_id=1, content="Morning content 2", start_time=3600, created_at=datetime.now(), updated_at=datetime.now()),
        Chunk(id=12, transcript_id=1, content="Noon content", start_time=14400, created_at=datetime.now(), updated_at=datetime.now()),
    ]

    with patch('transcript_engine.features.actionables_utils.crud') as mock_crud:
        mock_crud.get_transcript_ids_by_date_range.return_value = [1]
        mock_crud.get_transcript_by_id.return_value = transcript1
        mock_crud.get_chunks_by_transcript_id.return_value = chunks_t1

        result = get_transcript_for_timeframe(mock_db_connection, target_d, "morning")
        assert result == "Morning content 1\n\nMorning content 2"
        mock_crud.get_transcript_ids_by_date_range.assert_called_once()
        mock_crud.get_transcript_by_id.assert_called_once_with(mock_db_connection, 1)
        mock_crud.get_chunks_by_transcript_id.assert_called_once_with(mock_db_connection, 1)

@patch('transcript_engine.features.actionables_utils.get_settings')
def test_get_transcript_for_timeframe_afternoon_chunks_found(mock_get_settings, mock_db_connection, mock_settings):
    mock_get_settings.return_value = mock_settings
    target_d = date(2023, 10, 26)
    transcript_start = datetime(2023, 10, 26, 10, 0, 0, tzinfo=timezone.utc) # Transcript starts 10 AM
    transcript1 = Transcript(id=1, source="test", source_id="t1", start_time=transcript_start, created_at=datetime.now(),updated_at=datetime.now(), is_chunked=True)
    
    # Chunks relative to transcript_start (10 AM)
    # Chunk 1: 10 AM + 7200s (2hr) = 12:00 PM (afternoon)
    # Chunk 2: 10 AM + 10800s (3hr) = 1:00 PM (afternoon)
    # Chunk 3: 10 AM + 28800s (8hr) = 6:00 PM (evening - boundary, not in afternoon)
    chunks_t1 = [
        Chunk(id=20, transcript_id=1, content="Afternoon content 1", start_time=7200, created_at=datetime.now(),updated_at=datetime.now()),
        Chunk(id=21, transcript_id=1, content="Afternoon content 2", start_time=10800,created_at=datetime.now(),updated_at=datetime.now()),
        Chunk(id=22, transcript_id=1, content="Evening content early", start_time=28800,created_at=datetime.now(),updated_at=datetime.now()),
    ]

    with patch('transcript_engine.features.actionables_utils.crud') as mock_crud:
        mock_crud.get_transcript_ids_by_date_range.return_value = [1]
        mock_crud.get_transcript_by_id.return_value = transcript1
        mock_crud.get_chunks_by_transcript_id.return_value = chunks_t1

        result = get_transcript_for_timeframe(mock_db_connection, target_d, "afternoon")
        assert result == "Afternoon content 1\n\nAfternoon content 2"

@patch('transcript_engine.features.actionables_utils.get_settings')
def test_get_transcript_for_timeframe_no_chunks_in_window(mock_get_settings, mock_db_connection, mock_settings):
    mock_get_settings.return_value = mock_settings
    target_d = date(2023, 10, 26)
    transcript_start = datetime(2023, 10, 26, 14, 0, 0, tzinfo=timezone.utc) # Transcript starts 2 PM
    transcript1 = Transcript(id=1, source="test", source_id="t1", start_time=transcript_start, created_at=datetime.now(),updated_at=datetime.now(), is_chunked=True)
    chunks_t1 = [
        Chunk(id=30, transcript_id=1, content="Afternoon content far", start_time=0, created_at=datetime.now(),updated_at=datetime.now()), # 2 PM chunk
    ]

    with patch('transcript_engine.features.actionables_utils.crud') as mock_crud:
        mock_crud.get_transcript_ids_by_date_range.return_value = [1]
        mock_crud.get_transcript_by_id.return_value = transcript1
        mock_crud.get_chunks_by_transcript_id.return_value = chunks_t1

        result = get_transcript_for_timeframe(mock_db_connection, target_d, "morning") # Requesting morning
        assert result == ""

@patch('transcript_engine.features.actionables_utils.get_settings')
def test_get_transcript_for_timeframe_no_transcripts_for_date(mock_get_settings, mock_db_connection, mock_settings):
    mock_get_settings.return_value = mock_settings
    target_d = date(2023, 10, 26)

    with patch('transcript_engine.features.actionables_utils.crud') as mock_crud:
        mock_crud.get_transcript_ids_by_date_range.return_value = [] # No transcripts

        result = get_transcript_for_timeframe(mock_db_connection, target_d, "morning")
        assert result == ""
        mock_crud.get_transcript_by_id.assert_not_called()
        mock_crud.get_chunks_by_transcript_id.assert_not_called()

@patch('transcript_engine.features.actionables_utils.get_settings')
def test_get_transcript_for_timeframe_invalid_key(mock_get_settings, mock_db_connection, mock_settings):
    mock_get_settings.return_value = mock_settings
    target_d = date(2023, 10, 26)
    result = get_transcript_for_timeframe(mock_db_connection, target_d, "midnight_snack")
    assert result is None

@patch('transcript_engine.features.actionables_utils.get_settings')
def test_get_transcript_for_timeframe_transcript_without_start_time(mock_get_settings, mock_db_connection, mock_settings):
    mock_get_settings.return_value = mock_settings
    target_d = date(2023, 10, 26)
    transcript1 = Transcript(id=1, source="test", source_id="t1", start_time=None, created_at=datetime.now(),updated_at=datetime.now(), is_chunked=True)
    
    with patch('transcript_engine.features.actionables_utils.crud') as mock_crud:
        mock_crud.get_transcript_ids_by_date_range.return_value = [1]
        mock_crud.get_transcript_by_id.return_value = transcript1

        result = get_transcript_for_timeframe(mock_db_connection, target_d, "morning")
        assert result == "" # Should return empty as transcript is skipped
        mock_crud.get_chunks_by_transcript_id.assert_not_called()

@patch('transcript_engine.features.actionables_utils.get_settings')
def test_get_transcript_for_timeframe_chunk_without_start_time(mock_get_settings, mock_db_connection, mock_settings):
    mock_get_settings.return_value = mock_settings
    target_d = date(2023, 10, 26)
    transcript_start = datetime(2023, 10, 26, 8, 0, 0, tzinfo=timezone.utc)
    transcript1 = Transcript(id=1, source="test", source_id="t1", start_time=transcript_start, created_at=datetime.now(),updated_at=datetime.now(), is_chunked=True)
    chunks_t1 = [
        Chunk(id=40, transcript_id=1, content="Valid morning content", start_time=0, created_at=datetime.now(),updated_at=datetime.now()),
        Chunk(id=41, transcript_id=1, content="Chunk with no start time", start_time=None, created_at=datetime.now(),updated_at=datetime.now()),
    ]

    with patch('transcript_engine.features.actionables_utils.crud') as mock_crud:
        mock_crud.get_transcript_ids_by_date_range.return_value = [1]
        mock_crud.get_transcript_by_id.return_value = transcript1
        mock_crud.get_chunks_by_transcript_id.return_value = chunks_t1

        result = get_transcript_for_timeframe(mock_db_connection, target_d, "morning")
        assert result == "Valid morning content"

@patch('transcript_engine.features.actionables_utils.get_settings')
def test_get_transcript_for_timeframe_multiple_transcripts_same_day(mock_get_settings, mock_db_connection, mock_settings):
    mock_get_settings.return_value = mock_settings
    target_d = date(2023, 10, 26)

    # Transcript 1: 9 AM
    t1_start = datetime(2023, 10, 26, 9, 0, 0, tzinfo=timezone.utc)
    transcript1 = Transcript(id=1, source="test", source_id="t1", start_time=t1_start, created_at=datetime.now(),updated_at=datetime.now(), is_chunked=True)
    chunks_t1 = [Chunk(id=50, transcript_id=1, content="T1 Morning", start_time=0, created_at=datetime.now(),updated_at=datetime.now())] # 9:00 AM

    # Transcript 2: 10 AM
    t2_start = datetime(2023, 10, 26, 10, 0, 0, tzinfo=timezone.utc)
    transcript2 = Transcript(id=2, source="test", source_id="t2", start_time=t2_start, created_at=datetime.now(),updated_at=datetime.now(), is_chunked=True)
    chunks_t2 = [Chunk(id=51, transcript_id=2, content="T2 Morning", start_time=0, created_at=datetime.now(),updated_at=datetime.now())] # 10:00 AM
    
    # Transcript 3: 2 PM (should not be included in morning)
    t3_start = datetime(2023, 10, 26, 14, 0, 0, tzinfo=timezone.utc)
    transcript3 = Transcript(id=3, source="test", source_id="t3", start_time=t3_start, created_at=datetime.now(),updated_at=datetime.now(), is_chunked=True)
    chunks_t3 = [Chunk(id=52, transcript_id=3, content="T3 Afternoon", start_time=0, created_at=datetime.now(),updated_at=datetime.now())]

    def get_transcript_by_id_side_effect(db, id_):
        if id_ == 1: return transcript1
        if id_ == 2: return transcript2
        if id_ == 3: return transcript3
        return None

    def get_chunks_by_transcript_id_side_effect(db, id_):
        if id_ == 1: return chunks_t1
        if id_ == 2: return chunks_t2
        if id_ == 3: return chunks_t3
        return []

    with patch('transcript_engine.features.actionables_utils.crud') as mock_crud:
        mock_crud.get_transcript_ids_by_date_range.return_value = [1, 2, 3]
        mock_crud.get_transcript_by_id.side_effect = get_transcript_by_id_side_effect
        mock_crud.get_chunks_by_transcript_id.side_effect = get_chunks_by_transcript_id_side_effect

        result = get_transcript_for_timeframe(mock_db_connection, target_d, "morning")
        assert result == "T1 Morning\n\nT2 Morning"

@patch('transcript_engine.features.actionables_utils.get_settings')
def test_get_transcript_for_timeframe_evening_boundary(mock_get_settings, mock_db_connection, mock_settings):
    mock_get_settings.return_value = mock_settings
    target_d = date(2023, 10, 26)
    # Transcript starts at 5 PM
    transcript_start = datetime(2023, 10, 26, 17, 0, 0, tzinfo=timezone.utc)
    transcript1 = Transcript(id=1, source="test", source_id="t1", start_time=transcript_start, created_at=datetime.now(),updated_at=datetime.now(), is_chunked=True)
    
    # Chunks relative to 5 PM start
    # Chunk 1: 5 PM + 0s = 17:00 (afternoon)
    # Chunk 2: 5 PM + 3599s = 17:59:59 (afternoon)
    # Chunk 3: 5 PM + 3600s = 18:00 (evening)
    # Chunk 4: 5 PM + (6 * 3600) - 1s = 22:59:59 (evening)
    # Chunk 5: 5 PM + (7 * 3600) = 00:00 next day (not evening of target_d)
    chunks_t1 = [
        Chunk(id=60, transcript_id=1, content="Late Afternoon 1", start_time=0, created_at=datetime.now(),updated_at=datetime.now()),
        Chunk(id=61, transcript_id=1, content="Late Afternoon 2", start_time=3599, created_at=datetime.now(),updated_at=datetime.now()),
        Chunk(id=62, transcript_id=1, content="Evening Start", start_time=3600, created_at=datetime.now(),updated_at=datetime.now()),
        Chunk(id=63, transcript_id=1, content="Late Evening", start_time=(6 * 3600) -1 , created_at=datetime.now(),updated_at=datetime.now()),
        Chunk(id=64, transcript_id=1, content="Next Day", start_time=(7*3600), created_at=datetime.now(),updated_at=datetime.now()),
    ]

    with patch('transcript_engine.features.actionables_utils.crud') as mock_crud:
        mock_crud.get_transcript_ids_by_date_range.return_value = [1]
        mock_crud.get_transcript_by_id.return_value = transcript1
        mock_crud.get_chunks_by_transcript_id.return_value = chunks_t1

        result_afternoon = get_transcript_for_timeframe(mock_db_connection, target_d, "afternoon")
        assert result_afternoon == "Late Afternoon 1\n\nLate Afternoon 2"

        result_evening = get_transcript_for_timeframe(mock_db_connection, target_d, "evening")
        assert result_evening == "Evening Start\n\nLate Evening"

# Consider adding a test for transcript spanning midnight if relevant to how data is stored/retrieved.
# Current logic for get_transcript_ids_by_date_range focuses on transcripts *overlapping* the day,
# and then chunk filtering is strict to the target_date and timeframe hours.
# So a chunk from a transcript that started yesterday but the chunk itself is on target_date in timeframe, it should be included.
# A chunk from a transcript starting target_date but chunk is on next day, it should be excluded.

@patch('transcript_engine.features.actionables_utils.get_settings')
def test_get_transcript_for_timeframe_chunk_on_target_date_from_prev_day_transcript(mock_get_settings, mock_db_connection, mock_settings):
    mock_get_settings.return_value = mock_settings
    target_d = date(2023, 10, 26)

    # Transcript started late on 25th (previous day)
    transcript1_start_utc = datetime(2023, 10, 25, 23, 0, 0, tzinfo=timezone.utc)
    transcript1 = Transcript(
        id=1, source="test", source_id="t1", start_time=transcript1_start_utc, created_at=datetime.now(),updated_at=datetime.now(), is_chunked=True
    )
    
    # Chunks relative to transcript1_start_utc (Oct 25, 11 PM UTC)
    # Chunk 1: 25th, 11 PM + 0s = 25th, 23:00 (not target date)
    # Chunk 2: 25th, 11 PM + 7200s (2hr) = 26th, 01:00 UTC (target date, but not in "morning" timeframe 6-12)
    # Chunk 3: 25th, 11 PM + (7*3600)s (7hr) = 26th, 06:00 UTC (target date, morning)
    chunks_t1 = [
        Chunk(id=70, transcript_id=1, content="Prev day content", start_time=0, created_at=datetime.now(),updated_at=datetime.now()),
        Chunk(id=71, transcript_id=1, content="Target day, wrong time", start_time=7200, created_at=datetime.now(),updated_at=datetime.now()),
        Chunk(id=72, transcript_id=1, content="Target day, correct time", start_time=(7*3600), created_at=datetime.now(),updated_at=datetime.now()),
    ]

    with patch('transcript_engine.features.actionables_utils.crud') as mock_crud:
        # Assume get_transcript_ids_by_date_range for 26th correctly returns transcript_id 1 
        # because it might span into the 26th (its end_time could be on 26th)
        mock_crud.get_transcript_ids_by_date_range.return_value = [1]
        mock_crud.get_transcript_by_id.return_value = transcript1
        mock_crud.get_chunks_by_transcript_id.return_value = chunks_t1

        result = get_transcript_for_timeframe(mock_db_connection, target_d, "morning")
        assert result == "Target day, correct time"

        result_full_day = get_transcript_for_timeframe(mock_db_connection, target_d, "full_day")
        # Chunk 71 (01:00 on target_date) and 72 (06:00 on target_date) should be included in full_day for target_date
        assert result_full_day == "Target day, wrong time\n\nTarget day, correct time" 