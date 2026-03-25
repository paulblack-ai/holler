"""Streaming voice pipeline coordinator.

Orchestrates the async flow: Audio -> VAD -> STT -> LLM -> TTS -> Audio.
No stage waits for the previous stage to fully complete (D-07).
Handles barge-in by cancelling TTS and re-entering listening state (D-10).

When a ToolExecutor is provided, the pipeline intercepts ToolCallSentinel
from the LLM stream, executes the tool, feeds the result back, and continues
the conversation (D-14, AGENT-01). TTS is flushed before tool execution to
prevent pipeline deadlock (Pitfall 2).
"""
import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Callable, Dict, Optional

import numpy as np
import structlog

from holler.core.voice.vad import VADState, VADEvent, PipelineState, VADConfig
from holler.core.voice.stt import STTEngine, STTConfig
from holler.core.voice.tts import TTSEngine, TTSConfig
from holler.core.voice.llm import LLMClient, LLMConfig
from holler.core.voice.resampler import downsample_24k_to_8k
from holler.core.agent.tools import ToolCallSentinel, get_tools

if TYPE_CHECKING:
    from holler.core.agent.executor import ToolExecutor

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

    When tool_executor is provided, the pipeline handles LLM tool invocations:
    intercepts ToolCallSentinel, executes via ToolExecutor, feeds result back
    to LLM for follow-up response. Backward compatible when tool_executor=None.
    """

    def __init__(
        self,
        stt_config: Optional[STTConfig] = None,
        tts_config: Optional[TTSConfig] = None,
        llm_config: Optional[LLMConfig] = None,
        vad_config: Optional[VADConfig] = None,
        tool_executor: Optional["ToolExecutor"] = None,
        on_optout: Optional[Callable] = None,
        opt_out_keywords: Optional[list] = None,
    ):
        self.stt = STTEngine(stt_config)
        self.tts = TTSEngine(tts_config)
        self.llm = LLMClient(llm_config)
        self.vad_config = vad_config or VADConfig()
        self.tool_executor = tool_executor
        self._on_optout = on_optout
        self._opt_out_keywords = opt_out_keywords or []
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
        """Run the STT -> LLM -> TTS pipeline for a complete turn.

        Supports tool-call interception when tool_executor is set:
        1. STT transcribes speech.
        2. LLM streams tokens (with tool definitions if tool_executor set).
        3. TTS consumes tokens and sends audio.
        4. If ToolCallSentinel received: flush TTS, execute tool, feed result
           back to LLM, continue for up to max_tool_rounds rounds.

        When tool_executor is None, behaves exactly as the original text-only
        pipeline (backward compatible).
        """
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

            # STT keyword opt-out check (COMP-04, D-03)
            if self._opt_out_keywords and transcript:
                from holler.core.telecom.optout import check_optout_keywords  # avoid circular import
                matched = check_optout_keywords(transcript, self._opt_out_keywords)
                if matched:
                    logger.info(
                        "pipeline.optout_detected",
                        call_uuid=session.call_uuid,
                        keyword=matched,
                        transcript=transcript[:100],
                    )
                    if self._on_optout:
                        await self._on_optout(session.call_uuid, matched)
                    session.vad.set_pipeline_state(PipelineState.LISTENING)
                    return  # Do NOT send transcript to LLM

            # Tool-call loop: LLM may return tool calls requiring re-prompting.
            # max_tool_rounds prevents infinite loops.
            max_tool_rounds = 5
            messages_for_round = transcript  # First round uses the transcript
            extra_history = []              # Tool results accumulated per round

            full_response = []  # Final text response tokens (for history)

            for round_num in range(max_tool_rounds):
                session.vad.set_pipeline_state(PipelineState.SPEAKING)
                session._tts_cancel.clear()

                token_queue: asyncio.Queue = asyncio.Queue()
                round_response: list = []
                tool_sentinel: Optional[ToolCallSentinel] = None

                tools = get_tools() if self.tool_executor else None
                history = session.history + extra_history

                async def feed_tokens(
                    _transcript=messages_for_round,
                    _history=history,
                    _tools=tools,
                ):
                    nonlocal tool_sentinel
                    async for token in self.llm.stream_response(_transcript, _history, tools=_tools):
                        if session._tts_cancel.is_set():
                            break
                        if isinstance(token, ToolCallSentinel):
                            # Flush TTS (prevents deadlock — Pitfall 2)
                            tool_sentinel = token
                            await token_queue.put(None)
                            return
                        await token_queue.put(token)
                        round_response.append(token)
                    await token_queue.put(None)  # Normal end sentinel

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

                if tool_sentinel and self.tool_executor:
                    # Execute tool calls and accumulate results
                    tool_results = []
                    for tc in tool_sentinel.tool_calls:
                        raw_args = tc["arguments"]
                        args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        logger.info(
                            "pipeline.tool_call",
                            call_uuid=session.call_uuid,
                            tool=tc["name"],
                            args=args,
                        )
                        result = await self.tool_executor.execute(tc["name"], args, session)
                        logger.info(
                            "pipeline.tool_result",
                            call_uuid=session.call_uuid,
                            tool=tc["name"],
                            result=result,
                        )
                        tool_results.append({"tool_call_id": tc["id"], "result": result})

                    # Build history entries for the next LLM round
                    # Assistant turn with tool_calls (role=assistant, content=None)
                    extra_history.append({
                        "role": "assistant",
                        "content": None,
                        "tool_calls": [
                            {
                                "id": tc["id"],
                                "type": "function",
                                "function": {
                                    "name": tc["name"],
                                    "arguments": tc["arguments"],
                                },
                            }
                            for tc in tool_sentinel.tool_calls
                        ],
                    })
                    # Tool result turns (role=tool)
                    for tr in tool_results:
                        extra_history.append(
                            self.llm.build_tool_result_entry(tr["tool_call_id"], tr["result"])
                        )

                    messages_for_round = ""  # LLM continues from tool results
                    tool_sentinel = None
                    continue  # Next round

                else:
                    # Normal text response — collect tokens and done
                    full_response = round_response
                    break

            # Update conversation history with user turn and final assistant turn
            session.history.append({"role": "user", "content": transcript})
            if full_response:
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
