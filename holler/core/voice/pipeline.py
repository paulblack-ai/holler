"""Streaming voice pipeline coordinator.

Orchestrates the async flow: Audio -> VAD -> STT -> LLM -> TTS -> Audio.
No stage waits for the previous stage to fully complete (D-07).
Handles barge-in by cancelling TTS and re-entering listening state (D-10).
"""
import asyncio
import time
from dataclasses import dataclass, field
from typing import Callable, Dict, Optional

import numpy as np
import structlog

from holler.core.voice.vad import VADState, VADEvent, PipelineState, VADConfig
from holler.core.voice.stt import STTEngine, STTConfig
from holler.core.voice.tts import TTSEngine, TTSConfig
from holler.core.voice.llm import LLMClient, LLMConfig
from holler.core.voice.resampler import downsample_24k_to_8k

logger = structlog.get_logger()


@dataclass
class VoiceSession:
    """Per-call voice session state."""
    call_uuid: str
    session_uuid: str
    history: list = field(default_factory=list)
    audio_buffer: np.ndarray = field(default_factory=lambda: np.array([], dtype=np.float32))
    vad: VADState = field(default_factory=VADState)
    is_active: bool = True
    tts_task: Optional[asyncio.Task] = None
    _tts_cancel: asyncio.Event = field(default_factory=asyncio.Event)


class VoicePipeline:
    """Streaming voice pipeline: Audio -> VAD -> STT -> LLM -> TTS -> Audio.

    One pipeline instance is shared across all calls. Each call gets a VoiceSession.
    STT and TTS engines are initialized once at startup and shared.
    """

    def __init__(
        self,
        stt_config: Optional[STTConfig] = None,
        tts_config: Optional[TTSConfig] = None,
        llm_config: Optional[LLMConfig] = None,
        vad_config: Optional[VADConfig] = None,
    ):
        self.stt = STTEngine(stt_config)
        self.tts = TTSEngine(tts_config)
        self.llm = LLMClient(llm_config)
        self.vad_config = vad_config or VADConfig()
        self._sessions: Dict[str, VoiceSession] = {}

    async def initialize(self) -> None:
        """Initialize STT, TTS, and LLM. Call once at startup."""
        await self.stt.initialize()
        await self.tts.initialize()
        await self.llm.initialize()
        logger.info("pipeline.initialized")

    def create_session(self, call_uuid: str, session_uuid: str) -> VoiceSession:
        """Create a new voice session for a call."""
        session = VoiceSession(
            call_uuid=call_uuid,
            session_uuid=session_uuid,
            vad=VADState(self.vad_config),
        )
        self._sessions[call_uuid] = session
        logger.info("pipeline.session_created", call_uuid=call_uuid)
        return session

    def remove_session(self, call_uuid: str) -> None:
        """Clean up a voice session."""
        session = self._sessions.pop(call_uuid, None)
        if session:
            session.is_active = False
            if session.tts_task and not session.tts_task.done():
                session.tts_task.cancel()
            logger.info("pipeline.session_removed", call_uuid=call_uuid)

    async def process_audio_chunk(
        self,
        call_uuid: str,
        pcm_16k: np.ndarray,
        send_audio_callback: Callable,
    ) -> None:
        """Process an incoming audio chunk through the pipeline.

        Args:
            call_uuid: FreeSWITCH call UUID
            pcm_16k: Audio data as float32 numpy array at 16kHz
            send_audio_callback: async callable(bytes) to send TTS audio back to FreeSWITCH
        """
        session = self._sessions.get(call_uuid)
        if not session or not session.is_active:
            return

        # VAD check — is there speech?
        is_speech = self._detect_speech(pcm_16k)
        vad_event = session.vad.on_audio_frame(is_speech)

        if vad_event == VADEvent.BARGE_IN:
            # Cancel TTS immediately (D-10, VOICE-06)
            await self._handle_barge_in(session)
            return

        if vad_event == VADEvent.SPEECH_START or vad_event == VADEvent.SPEECH_CONTINUE:
            # Accumulate audio in buffer
            session.audio_buffer = np.concatenate([session.audio_buffer, pcm_16k])

        elif vad_event == VADEvent.TURN_COMPLETE:
            # Human finished speaking — process through STT -> LLM -> TTS
            audio_to_transcribe = session.audio_buffer.copy()
            session.audio_buffer = np.array([], dtype=np.float32)
            session.vad.set_pipeline_state(PipelineState.PROCESSING)

            # Fire-and-forget the response pipeline
            session.tts_task = asyncio.create_task(
                self._respond(session, audio_to_transcribe, send_audio_callback)
            )

    def _detect_speech(self, pcm_16k: np.ndarray) -> bool:
        """Simple energy-based speech detection for pipeline use.

        The main VAD gating happens inside faster-whisper (vad_filter=True).
        This is a quick pre-filter for the pipeline state machine.
        """
        energy = np.sqrt(np.mean(pcm_16k ** 2))
        return bool(energy > 0.01)  # Threshold tunable

    async def _respond(
        self,
        session: VoiceSession,
        audio_16k: np.ndarray,
        send_audio_callback: Callable,
    ) -> None:
        """Run the STT -> LLM -> TTS pipeline for a complete turn."""
        turn_start = time.monotonic()

        try:
            # STT
            segments = await self.stt.transcribe_buffer(audio_16k)
            transcript = " ".join(segments).strip()
            if not transcript:
                session.vad.set_pipeline_state(PipelineState.LISTENING)
                return

            stt_time = time.monotonic()
            logger.info(
                "pipeline.stt_complete",
                call_uuid=session.call_uuid,
                transcript=transcript[:100],
                duration_ms=round((stt_time - turn_start) * 1000),
            )

            # LLM streaming -> TTS streaming
            session.vad.set_pipeline_state(PipelineState.SPEAKING)
            session._tts_cancel.clear()

            token_queue: asyncio.Queue = asyncio.Queue()
            full_response = []

            # Start LLM streaming into token queue
            async def feed_tokens():
                async for token in self.llm.stream_response(transcript, session.history):
                    if session._tts_cancel.is_set():
                        break
                    await token_queue.put(token)
                    full_response.append(token)
                await token_queue.put(None)  # Sentinel

            llm_task = asyncio.create_task(feed_tokens())

            # TTS streaming from token queue -> send audio back
            first_audio = True
            async for samples, sample_rate in self.tts.synthesize_stream(token_queue):
                if session._tts_cancel.is_set():
                    break
                if first_audio:
                    ttfa = time.monotonic()
                    logger.info(
                        "pipeline.first_audio",
                        call_uuid=session.call_uuid,
                        total_latency_ms=round((ttfa - turn_start) * 1000),
                    )
                    first_audio = False
                # Downsample from 24kHz to 8kHz and send to FreeSWITCH
                pcm_bytes = downsample_24k_to_8k(samples)
                await send_audio_callback(pcm_bytes)

            await llm_task

            # Update conversation history
            session.history.append({"role": "user", "content": transcript})
            session.history.append({"role": "assistant", "content": "".join(full_response)})

            turn_end = time.monotonic()
            logger.info(
                "pipeline.turn_complete",
                call_uuid=session.call_uuid,
                total_ms=round((turn_end - turn_start) * 1000),
            )

        except asyncio.CancelledError:
            logger.info("pipeline.turn_cancelled", call_uuid=session.call_uuid)
        except Exception as e:
            logger.error("pipeline.turn_error", call_uuid=session.call_uuid, error=str(e))
        finally:
            session.vad.set_pipeline_state(PipelineState.LISTENING)

    async def _handle_barge_in(self, session: VoiceSession) -> None:
        """Handle barge-in: cancel TTS, flush buffers, re-enter listening."""
        session._tts_cancel.set()
        if session.tts_task and not session.tts_task.done():
            session.tts_task.cancel()
        session.audio_buffer = np.array([], dtype=np.float32)
        session.vad.set_pipeline_state(PipelineState.LISTENING)
        logger.info("pipeline.barge_in", call_uuid=session.call_uuid)
