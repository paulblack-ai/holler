"""Tests for VAD state machine.

Tests cover:
- PipelineState enum values
- VADEvent enum values
- VADState initial state
- State transitions: LISTENING -> speech detected -> silence -> TURN_COMPLETE
- BARGE_IN detection during SPEAKING state
- Barge-in grace window (no BARGE_IN within first 500ms of SPEAKING)
- Configurable silence threshold
- Explicit timestamps for deterministic testing
"""
import pytest

from holler.core.voice.vad import (
    PipelineState,
    VADEvent,
    VADConfig,
    VADState,
)


class TestPipelineStateEnum:
    def test_has_listening(self):
        assert PipelineState.LISTENING.value == "listening"

    def test_has_speaking(self):
        assert PipelineState.SPEAKING.value == "speaking"

    def test_has_processing(self):
        assert PipelineState.PROCESSING.value == "processing"


class TestVADEventEnum:
    def test_has_speech_start(self):
        assert VADEvent.SPEECH_START.value == "speech_start"

    def test_has_turn_complete(self):
        assert VADEvent.TURN_COMPLETE.value == "turn_complete"

    def test_has_barge_in(self):
        assert VADEvent.BARGE_IN.value == "barge_in"

    def test_has_speech_continue(self):
        assert VADEvent.SPEECH_CONTINUE.value == "speech_continue"

    def test_has_silence(self):
        assert VADEvent.SILENCE.value == "silence"

    def test_has_none(self):
        assert VADEvent.NONE.value == "none"


class TestVADConfig:
    def test_default_silence_threshold(self):
        config = VADConfig()
        assert config.silence_threshold_ms == 700.0

    def test_default_barge_in_grace(self):
        config = VADConfig()
        assert config.barge_in_grace_ms == 500.0

    def test_configurable_silence_threshold(self):
        config = VADConfig(silence_threshold_ms=300.0)
        assert config.silence_threshold_ms == 300.0


class TestVADStateInitial:
    def test_starts_in_listening(self):
        vad = VADState()
        assert vad.pipeline_state == PipelineState.LISTENING

    def test_speech_not_active_initially(self):
        vad = VADState()
        assert not vad._speech_active


class TestVADStateSpeechDetection:
    def test_first_speech_frame_returns_speech_start(self):
        """LISTENING + is_speech=True on first speech -> SPEECH_START."""
        vad = VADState()
        event = vad.on_audio_frame(is_speech=True, timestamp=0.0)
        assert event == VADEvent.SPEECH_START

    def test_subsequent_speech_frames_return_speech_continue(self):
        """LISTENING + is_speech=True after speech started -> SPEECH_CONTINUE."""
        vad = VADState()
        vad.on_audio_frame(is_speech=True, timestamp=0.0)  # SPEECH_START
        event = vad.on_audio_frame(is_speech=True, timestamp=0.02)
        assert event == VADEvent.SPEECH_CONTINUE

    def test_silence_before_speech_returns_silence(self):
        """LISTENING + is_speech=False before any speech -> SILENCE or NONE."""
        vad = VADState()
        event = vad.on_audio_frame(is_speech=False, timestamp=0.0)
        assert event in (VADEvent.SILENCE, VADEvent.NONE)


class TestVADStateTurnDetection:
    def test_silence_starts_turn_detection_timer(self):
        """After speech, silence within threshold does not yet trigger TURN_COMPLETE."""
        vad = VADState()
        vad.on_audio_frame(is_speech=True, timestamp=0.0)  # SPEECH_START
        # Silence for 300ms (less than 700ms threshold)
        event = vad.on_audio_frame(is_speech=False, timestamp=0.3)
        assert event != VADEvent.TURN_COMPLETE

    def test_turn_complete_after_700ms_silence(self):
        """After 700ms of silence following speech, returns TURN_COMPLETE."""
        vad = VADState()
        vad.on_audio_frame(is_speech=True, timestamp=0.0)  # SPEECH_START
        vad.on_audio_frame(is_speech=False, timestamp=0.1)  # start silence timer
        # Continue silence past threshold
        event = vad.on_audio_frame(is_speech=False, timestamp=0.9)  # 800ms of silence
        assert event == VADEvent.TURN_COMPLETE

    def test_turn_complete_resets_speech_active(self):
        """After TURN_COMPLETE, speech is no longer active."""
        vad = VADState()
        vad.on_audio_frame(is_speech=True, timestamp=0.0)
        vad.on_audio_frame(is_speech=False, timestamp=0.1)
        vad.on_audio_frame(is_speech=False, timestamp=0.9)  # TURN_COMPLETE
        assert not vad._speech_active

    def test_configurable_300ms_threshold(self):
        """With 300ms threshold, TURN_COMPLETE fires after 300ms of silence."""
        config = VADConfig(silence_threshold_ms=300.0)
        vad = VADState(config=config)
        vad.on_audio_frame(is_speech=True, timestamp=0.0)
        vad.on_audio_frame(is_speech=False, timestamp=0.1)
        # 250ms of silence - should NOT trigger with 300ms threshold
        event = vad.on_audio_frame(is_speech=False, timestamp=0.35)
        assert event != VADEvent.TURN_COMPLETE
        # 350ms of silence - should trigger
        event = vad.on_audio_frame(is_speech=False, timestamp=0.5)
        assert event == VADEvent.TURN_COMPLETE

    def test_speech_resets_silence_timer(self):
        """Speech frame after silence period resets the silence timer."""
        vad = VADState()
        vad.on_audio_frame(is_speech=True, timestamp=0.0)
        vad.on_audio_frame(is_speech=False, timestamp=0.1)
        # Resume speech before threshold
        vad.on_audio_frame(is_speech=True, timestamp=0.5)
        # Reset: silence must restart from this point
        event = vad.on_audio_frame(is_speech=False, timestamp=0.6)
        assert event != VADEvent.TURN_COMPLETE


class TestVADStateBargeIn:
    def test_speech_during_speaking_after_grace_returns_barge_in(self):
        """SPEAKING state + is_speech=True + grace window elapsed -> BARGE_IN."""
        vad = VADState()
        vad.set_pipeline_state(PipelineState.SPEAKING, timestamp=0.0)
        # More than 500ms after SPEAKING started
        event = vad.on_audio_frame(is_speech=True, timestamp=0.6)
        assert event == VADEvent.BARGE_IN

    def test_speech_during_speaking_within_grace_returns_none(self):
        """SPEAKING state + is_speech=True + within grace window -> NONE (no barge-in)."""
        vad = VADState()
        vad.set_pipeline_state(PipelineState.SPEAKING, timestamp=0.0)
        # Within 500ms grace window
        event = vad.on_audio_frame(is_speech=True, timestamp=0.3)
        assert event != VADEvent.BARGE_IN

    def test_no_barge_in_at_500ms_boundary(self):
        """Barge-in requires strictly > grace_ms, not just at the boundary."""
        vad = VADState()
        vad.set_pipeline_state(PipelineState.SPEAKING, timestamp=0.0)
        # Exactly at 500ms - within grace, not beyond
        event = vad.on_audio_frame(is_speech=True, timestamp=0.5)
        # Should not be BARGE_IN
        assert event != VADEvent.BARGE_IN

    def test_set_pipeline_state_records_speaking_start_time(self):
        """set_pipeline_state(SPEAKING) records the speaking start time."""
        vad = VADState()
        vad.set_pipeline_state(PipelineState.SPEAKING)
        assert vad._speaking_start_time is not None

    def test_set_pipeline_state_updates_pipeline_state(self):
        """set_pipeline_state updates the pipeline_state attribute."""
        vad = VADState()
        vad.set_pipeline_state(PipelineState.PROCESSING)
        assert vad.pipeline_state == PipelineState.PROCESSING
