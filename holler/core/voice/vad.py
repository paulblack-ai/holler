"""Voice Activity Detection state machine for the voice pipeline.

Tracks speech onset/offset, turn completion, and barge-in detection.
Uses Silero VAD speech probability from faster-whisper (VOICE-04).
Turn detection via silence threshold (D-09, VOICE-05).
Barge-in detection during TTS playback (D-10, VOICE-06).
"""
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class PipelineState(Enum):
    LISTENING = "listening"      # VAD active, feeding STT
    SPEAKING = "speaking"        # TTS playing, barge-in monitoring
    PROCESSING = "processing"    # STT->LLM in progress


class VADEvent(Enum):
    SPEECH_START = "speech_start"
    SPEECH_CONTINUE = "speech_continue"
    SILENCE = "silence"
    TURN_COMPLETE = "turn_complete"
    BARGE_IN = "barge_in"
    NONE = "none"


@dataclass
class VADConfig:
    silence_threshold_ms: float = 700.0     # D-09: silence after speech = end of turn
    barge_in_grace_ms: float = 500.0        # Anti-pattern: grace window after TTS starts
    min_speech_duration_ms: float = 100.0   # Ignore very short speech bursts (noise)


class VADState:
    """VAD state machine tracking speech onset/offset and pipeline state transitions.

    Designed to receive per-frame speech detection results and emit high-level
    pipeline events: SPEECH_START, SPEECH_CONTINUE, TURN_COMPLETE, BARGE_IN.

    Thread-safety: Not thread-safe. Use from a single asyncio task.
    """

    def __init__(self, config: Optional[VADConfig] = None):
        self.config = config or VADConfig()
        self.pipeline_state = PipelineState.LISTENING
        self._speech_active = False
        self._silence_start_time: Optional[float] = None
        self._speech_start_time: Optional[float] = None
        self._speaking_start_time: Optional[float] = None

    def set_pipeline_state(self, state: PipelineState, timestamp: Optional[float] = None) -> None:
        """Transition the pipeline state.

        Sets _speaking_start_time when entering SPEAKING state to track
        the barge-in grace window.

        Args:
            state: The new pipeline state.
            timestamp: Current time in seconds. Uses time.monotonic() if None.
                       Provide explicit timestamps in tests for determinism.
        """
        self.pipeline_state = state
        if state == PipelineState.SPEAKING:
            self._speaking_start_time = timestamp if timestamp is not None else time.monotonic()

    def on_audio_frame(self, is_speech: bool, timestamp: Optional[float] = None) -> VADEvent:
        """Process a single audio frame's VAD result.

        Args:
            is_speech: True if VAD detected speech in this frame
            timestamp: Frame timestamp in seconds (uses time.monotonic() if None).
                       Provide explicit timestamps in tests for determinism.

        Returns:
            VADEvent indicating what happened in this frame.
        """
        now = timestamp if timestamp is not None else time.monotonic()

        if self.pipeline_state == PipelineState.LISTENING:
            return self._handle_listening(is_speech, now)
        elif self.pipeline_state == PipelineState.SPEAKING:
            return self._handle_speaking(is_speech, now)
        else:
            # PROCESSING state: ignore audio frames
            return VADEvent.NONE

    def _handle_listening(self, is_speech: bool, now: float) -> VADEvent:
        """Handle audio frame in LISTENING state."""
        if is_speech:
            if not self._speech_active:
                # Speech onset
                self._speech_active = True
                self._speech_start_time = now
                self._silence_start_time = None
                return VADEvent.SPEECH_START
            else:
                # Continuing speech - reset silence timer if it was running
                self._silence_start_time = None
                return VADEvent.SPEECH_CONTINUE
        else:
            # Silence frame
            if self._speech_active:
                if self._silence_start_time is None:
                    # Start silence timer
                    self._silence_start_time = now

                silence_duration_ms = (now - self._silence_start_time) * 1000.0
                if silence_duration_ms >= self.config.silence_threshold_ms:
                    # Silence threshold exceeded - end of turn
                    self._speech_active = False
                    self._silence_start_time = None
                    self._speech_start_time = None
                    return VADEvent.TURN_COMPLETE
                else:
                    return VADEvent.SILENCE
            else:
                return VADEvent.SILENCE

    def _handle_speaking(self, is_speech: bool, now: float) -> VADEvent:
        """Handle audio frame in SPEAKING (TTS playback) state.

        Detects barge-in: user speaks while TTS is playing.
        Grace window: no barge-in within first barge_in_grace_ms of SPEAKING start.
        """
        if is_speech and self._speaking_start_time is not None:
            elapsed_ms = (now - self._speaking_start_time) * 1000.0
            if elapsed_ms > self.config.barge_in_grace_ms:
                return VADEvent.BARGE_IN
            # Within grace window - ignore speech
            return VADEvent.NONE

        return VADEvent.NONE
