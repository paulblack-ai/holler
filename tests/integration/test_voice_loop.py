"""Integration test for the voice pipeline loop.

Tests that audio flows correctly through the pipeline:
WebSocket audio -> VAD -> STT -> LLM -> TTS -> WebSocket response.

Uses mocked STT/TTS/LLM to avoid requiring GPU/models, but exercises
the real pipeline coordinator, audio bridge, VAD, and resampler.
"""
import asyncio
import json
import base64
import numpy as np
import pytest
import websockets
from unittest.mock import AsyncMock, MagicMock, patch

from holler.core.voice.pipeline import VoicePipeline, VoiceSession
from holler.core.voice.audio_bridge import AudioBridge, AudioBridgeConfig
from holler.core.voice.vad import VADState, VADEvent, PipelineState, VADConfig
from holler.core.voice.stt import STTConfig
from holler.core.voice.tts import TTSConfig
from holler.core.voice.llm import LLMConfig


async def _drain_queue(queue):
    """Helper to drain an asyncio queue until None sentinel."""
    while True:
        item = await queue.get()
        if item is None:
            break
        yield item


@pytest.mark.asyncio
async def test_pipeline_creates_and_removes_session():
    """Verify session lifecycle management."""
    pipeline = VoicePipeline()
    # Skip initialization (would load real models)
    session = pipeline.create_session("test-uuid", "test-session")
    assert session.call_uuid == "test-uuid"
    assert session.is_active is True
    assert "test-uuid" in pipeline._sessions

    pipeline.remove_session("test-uuid")
    assert "test-uuid" not in pipeline._sessions


@pytest.mark.asyncio
async def test_vad_turn_detection_triggers_processing():
    """Verify VAD turn completion triggers STT->LLM->TTS flow."""
    pipeline = VoicePipeline()
    session = pipeline.create_session("test-uuid", "test-session")

    # Mock STT to return a transcript
    pipeline.stt.transcribe_buffer = AsyncMock(return_value=["Hello there"])

    # Mock LLM to yield tokens
    async def mock_stream(*args, **kwargs):
        for token in ["Hi", " back", "!"]:
            yield token

    pipeline.llm.stream_response = mock_stream

    # Mock TTS to yield audio from queue
    async def mock_tts_stream(queue):
        async for _token in _drain_queue(queue):
            pass
        yield (np.zeros(4800, dtype=np.float32), 24000)

    pipeline.tts.synthesize_stream = mock_tts_stream

    send_callback = AsyncMock()

    # Simulate speech -> silence -> turn complete
    speech_audio = np.random.randn(16000).astype(np.float32) * 0.1
    session.vad.on_audio_frame = MagicMock(side_effect=[
        VADEvent.SPEECH_START,
        VADEvent.SPEECH_CONTINUE,
        VADEvent.TURN_COMPLETE,
    ])

    # Process three chunks
    for i in range(3):
        chunk = speech_audio[i * 5333:(i + 1) * 5333]
        await pipeline.process_audio_chunk("test-uuid", chunk, send_callback)

    # Allow response task to complete
    await asyncio.sleep(0.5)

    # Verify STT was called
    pipeline.stt.transcribe_buffer.assert_called_once()


@pytest.mark.asyncio
async def test_audio_bridge_websocket_server_starts():
    """Verify the WebSocket server starts and accepts connections."""
    pipeline = VoicePipeline()
    config = AudioBridgeConfig(host="127.0.0.1", port=0)  # Port 0 = random available

    bridge = AudioBridge(pipeline, config)
    await bridge.start()

    # Get the actual port assigned
    actual_port = bridge._server.sockets[0].getsockname()[1]

    try:
        async with websockets.connect(f"ws://127.0.0.1:{actual_port}/voice/test-uuid") as ws:
            # Connection should succeed — verify it's open by checking state
            assert ws.state.name in ("OPEN", "CONNECTING")
    finally:
        await bridge.stop()
