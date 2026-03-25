"""Tests for LLM tool-call streaming and pipeline tool-call interception.

Covers:
- LLMClient.stream_response() backward compat (text-only, no tools)
- LLMClient.stream_response() with tools yielding ToolCallSentinel
- ToolCallSentinel accumulation from streaming chunks
- build_tool_result_entry() format
- VoicePipeline._respond() without tool_executor (text-only backward compat)
- VoicePipeline._respond() with tool_executor intercepting ToolCallSentinel
- VoicePipeline._respond() feeding tool result back to LLM
- max_tool_rounds limit prevents infinite loop
"""
import asyncio
import json
from dataclasses import dataclass, field
from typing import AsyncGenerator, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

from holler.core.agent.tools import ToolCallSentinel, get_tools
from holler.core.voice.llm import LLMClient, LLMConfig


# ---------------------------------------------------------------------------
# Helpers: mock streaming chunk factories
# ---------------------------------------------------------------------------

def _make_text_chunk(content: str):
    """Build a mock streaming chunk with text content."""
    delta = MagicMock()
    delta.content = content
    delta.tool_calls = None
    choice = MagicMock()
    choice.delta = delta
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


def _make_tool_chunk(index: int, tc_id: Optional[str], name: Optional[str], arguments: Optional[str]):
    """Build a mock streaming chunk with a tool_calls delta."""
    tc = MagicMock()
    tc.index = index
    tc.id = tc_id
    tc.function = MagicMock()
    tc.function.name = name
    tc.function.arguments = arguments

    delta = MagicMock()
    delta.content = None
    delta.tool_calls = [tc]

    choice = MagicMock()
    choice.delta = delta
    chunk = MagicMock()
    chunk.choices = [choice]
    return chunk


async def _async_iter(items):
    """Yield items from an async generator."""
    for item in items:
        yield item


def run(coro):
    """Run a coroutine in a new event loop (pytest-asyncio not required)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# LLMClient tests
# ---------------------------------------------------------------------------

def _make_llm_client(chunks):
    """Return an initialized LLMClient whose create() returns the given chunks."""
    client = LLMClient(LLMConfig())
    mock_openai = MagicMock()

    async def fake_create(**kwargs):
        return _async_iter(chunks)

    mock_openai.chat.completions.create = fake_create
    client._client = mock_openai
    return client


def test_llm_stream_text_only_backward_compat():
    """stream_response() without tools yields only str tokens."""
    chunks = [_make_text_chunk("Hello"), _make_text_chunk(" world")]
    llm = _make_llm_client(chunks)

    async def _run():
        tokens = []
        async for token in llm.stream_response("hi"):
            tokens.append(token)
        return tokens

    tokens = run(_run())
    assert tokens == ["Hello", " world"]
    assert all(isinstance(t, str) for t in tokens)


def test_llm_stream_with_tools_yields_sentinel():
    """stream_response() with tools yields ToolCallSentinel when LLM returns tool_calls."""
    # First chunk: tool call starts with id and name
    # Second chunk: arguments fragment 1
    # Third chunk: arguments fragment 2
    chunks = [
        _make_tool_chunk(0, "call_abc123", "sms", None),
        _make_tool_chunk(0, None, None, '{"destination":'),
        _make_tool_chunk(0, None, None, '"+15550001234","message":"Hi"}'),
    ]
    llm = _make_llm_client(chunks)

    async def _run():
        results = []
        async for item in llm.stream_response("send a text", tools=get_tools()):
            results.append(item)
        return results

    results = run(_run())
    # Last item must be ToolCallSentinel
    assert len(results) == 1
    sentinel = results[0]
    assert isinstance(sentinel, ToolCallSentinel)


def test_llm_tool_call_accumulates_correctly():
    """ToolCallSentinel contains correctly accumulated tool call data."""
    chunks = [
        _make_tool_chunk(0, "call_abc123", "sms", None),
        _make_tool_chunk(0, None, None, '{"destination":"+15550001234"'),
        _make_tool_chunk(0, None, None, ',"message":"Hello"}'),
    ]
    llm = _make_llm_client(chunks)

    async def _run():
        results = []
        async for item in llm.stream_response("send", tools=get_tools()):
            results.append(item)
        return results

    results = run(_run())
    sentinel = results[-1]
    assert isinstance(sentinel, ToolCallSentinel)
    assert len(sentinel.tool_calls) == 1
    tc = sentinel.tool_calls[0]
    assert tc["id"] == "call_abc123"
    assert tc["name"] == "sms"
    # Arguments should be fully accumulated
    args = json.loads(tc["arguments"])
    assert args["destination"] == "+15550001234"
    assert args["message"] == "Hello"


def test_llm_text_before_no_tool_calls():
    """Text chunks followed by no tool_calls: no ToolCallSentinel yielded."""
    chunks = [_make_text_chunk("I'll help"), _make_text_chunk(" you.")]
    llm = _make_llm_client(chunks)

    async def _run():
        results = []
        async for item in llm.stream_response("help me", tools=get_tools()):
            results.append(item)
        return results

    results = run(_run())
    assert all(isinstance(r, str) for r in results)
    assert "".join(results) == "I'll help you."


def test_build_tool_result_entry():
    """build_tool_result_entry() returns dict with role=tool and JSON content."""
    llm = LLMClient()
    result = {"status": "ok", "message_id": "msg_123"}
    entry = llm.build_tool_result_entry("call_abc", result)

    assert entry["role"] == "tool"
    assert entry["tool_call_id"] == "call_abc"
    content = json.loads(entry["content"])
    assert content["status"] == "ok"
    assert content["message_id"] == "msg_123"


def test_build_tool_result_entry_serializes_nested():
    """build_tool_result_entry() handles nested dicts and encodes as JSON."""
    llm = LLMClient()
    result = {"status": "blocked", "reason": "DNC list", "details": {"rule": "TCPA"}}
    entry = llm.build_tool_result_entry("tc_id_999", result)
    parsed = json.loads(entry["content"])
    assert parsed["details"]["rule"] == "TCPA"


# ---------------------------------------------------------------------------
# VoicePipeline tool-call interception tests
# ---------------------------------------------------------------------------

def _make_pipeline_with_mocks(llm_items, tool_executor=None, tool_result=None):
    """Build a VoicePipeline with fully mocked STT, LLM, TTS components.

    Args:
        llm_items: List of items yielded by mock LLM (str tokens or ToolCallSentinel).
                   Can be a list of lists for multi-round responses.
        tool_executor: Optional mock ToolExecutor. If None, pipeline has no executor.
        tool_result: Result dict returned by tool_executor.execute() if provided.
    """
    from holler.core.voice.pipeline import VoicePipeline, VoiceSession
    from holler.core.voice.vad import VADState, VADConfig

    # Patch STT
    mock_stt = MagicMock()
    mock_stt.transcribe_buffer = AsyncMock(return_value=["send a text"])

    # Patch TTS: synthesize_stream returns no audio (just drains queue)
    async def fake_synthesize_stream(queue):
        while True:
            token = await queue.get()
            if token is None:
                break
            # Yield minimal audio so the pipeline progresses
            yield np.zeros(10, dtype=np.float32), 24000

    mock_tts = MagicMock()
    mock_tts.synthesize_stream = fake_synthesize_stream

    # Patch LLM — support multi-round responses
    if isinstance(llm_items[0], list):
        # Multi-round: each call returns next list
        rounds = list(llm_items)
        call_count = [0]

        async def multi_round_stream(transcript, history=None, tools=None):
            idx = call_count[0]
            call_count[0] += 1
            items = rounds[idx] if idx < len(rounds) else []
            for item in items:
                yield item

        mock_llm = MagicMock()
        mock_llm.stream_response = multi_round_stream
        mock_llm.build_tool_result_entry = LLMClient().build_tool_result_entry
    else:
        # Single round
        async def single_stream(transcript, history=None, tools=None):
            for item in llm_items:
                yield item

        mock_llm = MagicMock()
        mock_llm.stream_response = single_stream
        mock_llm.build_tool_result_entry = LLMClient().build_tool_result_entry

    # Build pipeline bypassing __init__ to inject mocks
    pipeline = VoicePipeline.__new__(VoicePipeline)
    pipeline.stt = mock_stt
    pipeline.tts = mock_tts
    pipeline.llm = mock_llm
    pipeline.vad_config = VADConfig()
    pipeline._sessions = {}
    pipeline.tool_executor = tool_executor

    return pipeline


def _make_voice_session(call_uuid="test-call-uuid"):
    """Create a minimal VoiceSession for testing."""
    from holler.core.voice.pipeline import VoiceSession
    from holler.core.voice.vad import VADState, VADConfig
    session = VoiceSession(
        call_uuid=call_uuid,
        session_uuid="test-session-uuid",
        vad=VADState(VADConfig()),
    )
    return session


def test_pipeline_respond_text_only_no_executor():
    """_respond() without tool_executor works exactly as before (text-only path)."""
    pipeline = _make_pipeline_with_mocks(["Hello", " there"])
    session = _make_voice_session()
    audio = np.zeros(1600, dtype=np.float32)
    audio_sent = []

    async def send_audio(pcm_bytes):
        audio_sent.append(pcm_bytes)

    run(pipeline._respond(session, audio, send_audio))

    # History should have user + assistant turns
    assert len(session.history) == 2
    assert session.history[0]["role"] == "user"
    assert session.history[1]["role"] == "assistant"
    assert session.history[1]["content"] == "Hello there"


def test_pipeline_respond_text_only_with_executor():
    """_respond() with tool_executor but text-only LLM response works as before."""
    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value={"status": "ok"})

    pipeline = _make_pipeline_with_mocks(["Normal", " response"], tool_executor=mock_executor)
    session = _make_voice_session()
    audio = np.zeros(1600, dtype=np.float32)

    run(pipeline._respond(session, audio, lambda _: asyncio.sleep(0)))

    # Tool executor should NOT have been called for text-only response
    mock_executor.execute.assert_not_called()
    assert session.history[1]["content"] == "Normal response"


def test_pipeline_respond_intercepts_tool_call():
    """_respond() with tool_executor intercepts ToolCallSentinel and calls execute()."""
    sentinel = ToolCallSentinel(tool_calls=[{
        "id": "call_abc",
        "name": "hangup",
        "arguments": '{"call_uuid": "some-uuid"}',
    }])
    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value={"status": "ok"})

    # Round 1: tool call. Round 2: follow-up text.
    pipeline = _make_pipeline_with_mocks(
        [[sentinel], ["Done."]],
        tool_executor=mock_executor,
    )
    session = _make_voice_session()
    audio = np.zeros(1600, dtype=np.float32)

    run(pipeline._respond(session, audio, lambda _: asyncio.sleep(0)))

    mock_executor.execute.assert_called_once()
    call_args = mock_executor.execute.call_args
    assert call_args[0][0] == "hangup"
    assert call_args[0][1] == {"call_uuid": "some-uuid"}


def test_pipeline_respond_feeds_tool_result_back():
    """_respond() feeds tool result back to LLM for follow-up response."""
    sentinel = ToolCallSentinel(tool_calls=[{
        "id": "call_xyz",
        "name": "sms",
        "arguments": '{"destination": "+15550001234", "message": "hi"}',
    }])
    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value={"status": "ok", "message_id": "msg_001"})

    # Round 1: tool call. Round 2: confirmation text.
    pipeline = _make_pipeline_with_mocks(
        [[sentinel], ["Message sent!"]],
        tool_executor=mock_executor,
    )
    session = _make_voice_session()
    audio = np.zeros(1600, dtype=np.float32)

    run(pipeline._respond(session, audio, lambda _: asyncio.sleep(0)))

    # Tool executor called
    mock_executor.execute.assert_called_once()
    # Final history should include user turn and assistant follow-up
    assert session.history[-1]["role"] == "assistant"
    assert session.history[-1]["content"] == "Message sent!"


def test_pipeline_max_tool_rounds_prevents_infinite_loop():
    """_respond() stops after max_tool_rounds to prevent infinite tool-call loops."""
    sentinel = ToolCallSentinel(tool_calls=[{
        "id": f"call_loop",
        "name": "hangup",
        "arguments": '{"call_uuid": "loop-uuid"}',
    }])
    mock_executor = MagicMock()
    mock_executor.execute = AsyncMock(return_value={"status": "ok"})

    # Always return a tool call — pipeline must stop after max_tool_rounds
    # Provide 10 rounds of sentinel to exceed the max
    pipeline = _make_pipeline_with_mocks(
        [[sentinel]] * 10,
        tool_executor=mock_executor,
    )
    session = _make_voice_session()
    audio = np.zeros(1600, dtype=np.float32)

    run(pipeline._respond(session, audio, lambda _: asyncio.sleep(0)))

    # Should have called execute at most max_tool_rounds=5 times
    assert mock_executor.execute.call_count <= 5


def test_pipeline_no_tool_executor_passes_none_tools():
    """_respond() without tool_executor calls stream_response() with tools=None."""
    from holler.core.voice.pipeline import VoicePipeline, VoiceSession
    from holler.core.voice.vad import VADState, VADConfig

    mock_stt = MagicMock()
    mock_stt.transcribe_buffer = AsyncMock(return_value=["hello"])

    async def fake_synth(queue):
        while True:
            token = await queue.get()
            if token is None:
                break
        return
        yield  # make it an async generator

    calls_made = []

    async def recording_stream(transcript, history=None, tools=None):
        calls_made.append({"transcript": transcript, "tools": tools})
        yield "Hi"

    mock_llm = MagicMock()
    mock_llm.stream_response = recording_stream
    mock_llm.build_tool_result_entry = LLMClient().build_tool_result_entry

    mock_tts = MagicMock()
    mock_tts.synthesize_stream = fake_synth

    pipeline = VoicePipeline.__new__(VoicePipeline)
    pipeline.stt = mock_stt
    pipeline.tts = mock_tts
    pipeline.llm = mock_llm
    pipeline.vad_config = VADConfig()
    pipeline._sessions = {}
    pipeline.tool_executor = None  # No executor

    session = VoiceSession(
        call_uuid="test", session_uuid="s1",
        vad=VADState(VADConfig()),
    )
    audio = np.zeros(1600, dtype=np.float32)
    run(pipeline._respond(session, audio, lambda _: asyncio.sleep(0)))

    assert len(calls_made) == 1
    assert calls_made[0]["tools"] is None
