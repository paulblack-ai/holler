"""Tests for recording module — start/stop recording and post-call transcription.

Tests cover:
- start_recording() sends uuid_setvar and uuid_record start ESL commands
- stop_recording() sends uuid_record stop ESL command
- recording_path() returns {recordings_dir}/{YYYY-MM-DD}/{call_uuid}.wav
- transcribe_recording() produces a .transcript.json file alongside the WAV
- transcript JSON contains "segments" list with start, end, text fields
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def run(coro):
    """Run a coroutine in a fresh event loop (no pytest-asyncio needed)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Test: recording_path returns correct path structure
# ---------------------------------------------------------------------------

def test_recording_path_structure():
    """recording_path() returns {recordings_dir}/{YYYY-MM-DD}/{call_uuid}.wav"""
    from holler.core.telecom.recording import recording_path

    with tempfile.TemporaryDirectory() as tmpdir:
        call_uuid = "test-call-uuid-001"
        path = recording_path(tmpdir, call_uuid)

        # Must end with the call_uuid.wav
        assert path.endswith(f"{call_uuid}.wav"), f"Expected path to end with {call_uuid}.wav, got: {path}"

        # Must contain a date-based subdirectory (YYYY-MM-DD format)
        path_obj = Path(path)
        date_dir = path_obj.parent.name
        # Date should match YYYY-MM-DD pattern
        parts = date_dir.split("-")
        assert len(parts) == 3, f"Expected YYYY-MM-DD date directory, got: {date_dir}"
        assert len(parts[0]) == 4, f"Expected 4-digit year, got: {parts[0]}"
        assert len(parts[1]) == 2, f"Expected 2-digit month, got: {parts[1]}"
        assert len(parts[2]) == 2, f"Expected 2-digit day, got: {parts[2]}"


def test_recording_path_creates_directory():
    """recording_path() creates the date-based subdirectory if it doesn't exist."""
    from holler.core.telecom.recording import recording_path

    with tempfile.TemporaryDirectory() as tmpdir:
        call_uuid = "test-call-uuid-002"
        path = recording_path(tmpdir, call_uuid)

        # The directory should be created
        assert Path(path).parent.exists(), f"Directory was not created: {Path(path).parent}"


# ---------------------------------------------------------------------------
# Test: start_recording sends correct ESL commands
# ---------------------------------------------------------------------------

def test_start_recording_sends_uuid_setvar():
    """start_recording() sends uuid_setvar for sample rate before starting record."""
    from holler.core.telecom.recording import start_recording

    esl = AsyncMock()
    esl.send_raw = AsyncMock(return_value="+OK")

    call_uuid = "call-abc-001"
    path = "/recordings/2026-03-24/call-abc-001.wav"

    run(start_recording(esl, call_uuid, path))

    # Check that send_raw was called (at least twice — setvar + record)
    assert esl.send_raw.await_count >= 2, f"Expected at least 2 send_raw calls, got {esl.send_raw.await_count}"

    # Check uuid_setvar for sample rate was called
    all_calls = [str(call) for call in esl.send_raw.await_args_list]
    setvar_called = any("uuid_setvar" in c and "record_sample_rate" in c for c in all_calls)
    assert setvar_called, f"Expected uuid_setvar record_sample_rate command, got calls: {all_calls}"


def test_start_recording_sends_uuid_record_start():
    """start_recording() sends uuid_record start command."""
    from holler.core.telecom.recording import start_recording

    esl = AsyncMock()
    esl.send_raw = AsyncMock(return_value="+OK")

    call_uuid = "call-abc-002"
    path = "/recordings/2026-03-24/call-abc-002.wav"

    run(start_recording(esl, call_uuid, path))

    all_calls = [str(call) for call in esl.send_raw.await_args_list]
    record_start_called = any(
        "uuid_record" in c and "start" in c and call_uuid in c
        for c in all_calls
    )
    assert record_start_called, f"Expected uuid_record {call_uuid} start command, got: {all_calls}"


def test_start_recording_includes_path():
    """start_recording() includes the recording path in the uuid_record command."""
    from holler.core.telecom.recording import start_recording

    esl = AsyncMock()
    esl.send_raw = AsyncMock(return_value="+OK")

    call_uuid = "call-abc-003"
    path = "/recordings/2026-03-24/call-abc-003.wav"

    run(start_recording(esl, call_uuid, path))

    all_calls = [str(call) for call in esl.send_raw.await_args_list]
    path_in_record_cmd = any("uuid_record" in c and path in c for c in all_calls)
    assert path_in_record_cmd, f"Expected path '{path}' in uuid_record command, got: {all_calls}"


# ---------------------------------------------------------------------------
# Test: stop_recording sends uuid_record stop command
# ---------------------------------------------------------------------------

def test_stop_recording_sends_uuid_record_stop():
    """stop_recording() sends uuid_record stop command."""
    from holler.core.telecom.recording import stop_recording

    esl = AsyncMock()
    esl.send_raw = AsyncMock(return_value="+OK")

    call_uuid = "call-def-001"
    path = "/recordings/2026-03-24/call-def-001.wav"

    run(stop_recording(esl, call_uuid, path))

    assert esl.send_raw.await_count >= 1
    all_calls = [str(call) for call in esl.send_raw.await_args_list]
    record_stop_called = any(
        "uuid_record" in c and "stop" in c and call_uuid in c
        for c in all_calls
    )
    assert record_stop_called, f"Expected uuid_record {call_uuid} stop command, got: {all_calls}"


def test_stop_recording_includes_path():
    """stop_recording() includes the recording path in the uuid_record stop command."""
    from holler.core.telecom.recording import stop_recording

    esl = AsyncMock()
    esl.send_raw = AsyncMock(return_value="+OK")

    call_uuid = "call-def-002"
    path = "/recordings/2026-03-24/call-def-002.wav"

    run(stop_recording(esl, call_uuid, path))

    all_calls = [str(call) for call in esl.send_raw.await_args_list]
    path_in_stop_cmd = any("uuid_record" in c and "stop" in c and path in c for c in all_calls)
    assert path_in_stop_cmd, f"Expected path '{path}' in uuid_record stop command, got: {all_calls}"


# ---------------------------------------------------------------------------
# Test: transcribe_recording produces .transcript.json file
# ---------------------------------------------------------------------------

def test_transcribe_recording_produces_json_file():
    """transcribe_recording() creates a .transcript.json file alongside the WAV."""
    from holler.core.telecom.recording import transcribe_recording

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = os.path.join(tmpdir, "test-call.wav")
        # Create a dummy WAV file
        Path(wav_path).write_bytes(b"RIFF" + b"\x00" * 40)

        # Mock the whisper model
        mock_model = MagicMock()
        mock_segment_1 = MagicMock()
        mock_segment_1.start = 0.0
        mock_segment_1.end = 2.5
        mock_segment_1.text = "Hello, this is a test."
        mock_segment_2 = MagicMock()
        mock_segment_2.start = 2.5
        mock_segment_2.end = 5.0
        mock_segment_2.text = "Please stop calling me."

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_model.transcribe = MagicMock(return_value=([mock_segment_1, mock_segment_2], mock_info))

        json_path = run(transcribe_recording(wav_path, mock_model))

        # JSON file should exist
        assert os.path.exists(json_path), f"Transcript JSON file was not created: {json_path}"

        # JSON file should be alongside the WAV
        expected_json_path = wav_path.replace(".wav", ".transcript.json")
        assert json_path == expected_json_path, f"Expected {expected_json_path}, got {json_path}"


def test_transcribe_recording_json_contains_segments():
    """transcribe_recording() produces JSON with 'segments' list with start, end, text fields."""
    from holler.core.telecom.recording import transcribe_recording

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = os.path.join(tmpdir, "test-call-2.wav")
        Path(wav_path).write_bytes(b"RIFF" + b"\x00" * 40)

        mock_model = MagicMock()
        mock_segment = MagicMock()
        mock_segment.start = 1.0
        mock_segment.end = 3.5
        mock_segment.text = "Hello there."

        mock_info = MagicMock()
        mock_info.language = "en"
        mock_model.transcribe = MagicMock(return_value=([mock_segment], mock_info))

        json_path = run(transcribe_recording(wav_path, mock_model))

        with open(json_path) as f:
            data = json.load(f)

        assert "segments" in data, f"Expected 'segments' key in transcript JSON, got keys: {list(data.keys())}"
        assert isinstance(data["segments"], list), f"Expected segments to be a list"
        assert len(data["segments"]) == 1

        seg = data["segments"][0]
        assert "start" in seg, "Segment missing 'start' field"
        assert "end" in seg, "Segment missing 'end' field"
        assert "text" in seg, "Segment missing 'text' field"
        assert seg["start"] == 1.0
        assert seg["end"] == 3.5
        assert seg["text"] == "Hello there."


def test_transcribe_recording_uses_run_in_executor():
    """transcribe_recording() uses run_in_executor for CPU-bound transcription."""
    from holler.core.telecom.recording import transcribe_recording

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = os.path.join(tmpdir, "test-call-3.wav")
        Path(wav_path).write_bytes(b"RIFF" + b"\x00" * 40)

        mock_model = MagicMock()
        mock_info = MagicMock()
        mock_info.language = "en"
        mock_model.transcribe = MagicMock(return_value=([], mock_info))

        executor_called = []

        async def test():
            loop = asyncio.get_event_loop()
            original_run_in_executor = loop.run_in_executor

            async def tracking_run_in_executor(executor, func, *args):
                executor_called.append(True)
                return await original_run_in_executor(executor, func, *args)

            with patch.object(loop, 'run_in_executor', side_effect=tracking_run_in_executor):
                await transcribe_recording(wav_path, mock_model)

        run(test())

        assert len(executor_called) > 0, "Expected run_in_executor to be called for CPU-bound transcription"


def test_transcribe_recording_json_includes_language():
    """transcribe_recording() JSON includes 'language' field from model info."""
    from holler.core.telecom.recording import transcribe_recording

    with tempfile.TemporaryDirectory() as tmpdir:
        wav_path = os.path.join(tmpdir, "test-call-4.wav")
        Path(wav_path).write_bytes(b"RIFF" + b"\x00" * 40)

        mock_model = MagicMock()
        mock_info = MagicMock()
        mock_info.language = "es"
        mock_model.transcribe = MagicMock(return_value=([], mock_info))

        json_path = run(transcribe_recording(wav_path, mock_model))

        with open(json_path) as f:
            data = json.load(f)

        assert "language" in data, "Expected 'language' key in transcript JSON"
        assert data["language"] == "es"
