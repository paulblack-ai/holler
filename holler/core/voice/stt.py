"""Speech-to-text engine wrapping faster-whisper.

Provides streaming transcription from 16kHz float32 audio chunks.
Uses Silero VAD (built into faster-whisper) to gate input (VOICE-01, VOICE-04).
"""
import asyncio
from dataclasses import dataclass, field
from typing import List, Optional

import numpy as np
import structlog

logger = structlog.get_logger()


@dataclass
class STTConfig:
    model_name: str = "distil-large-v3"
    device: str = "cpu"                  # "cuda" for GPU
    compute_type: str = "int8"           # "float16" for GPU
    language: str = "en"
    vad_filter: bool = True
    vad_min_silence_ms: int = 300
    vad_threshold: float = 0.5
    no_speech_prob_threshold: float = 0.6  # Pitfall 5: reject hallucinated segments
    min_chunk_duration_s: float = 0.5      # Don't transcribe < 500ms (Pitfall 5)
    buffer_trim_s: float = 0.5             # Keep last 0.5s of buffer for context


class STTEngine:
    """Streaming speech-to-text using faster-whisper.

    Model loading is deferred to initialize() — call once at startup,
    not per-call. This allows the engine to be constructed cheaply and
    initialized once when the application starts.
    """

    def __init__(self, config: Optional[STTConfig] = None):
        self.config = config or STTConfig()
        self._model = None

    async def initialize(self) -> None:
        """Load the Whisper model. Call once at startup, not per-call."""
        from faster_whisper import WhisperModel
        loop = asyncio.get_event_loop()
        self._model = await loop.run_in_executor(
            None,
            lambda: WhisperModel(
                self.config.model_name,
                device=self.config.device,
                compute_type=self.config.compute_type,
            )
        )
        logger.info("stt.initialized", model=self.config.model_name, device=self.config.device)

    async def transcribe_buffer(self, audio_16k: np.ndarray) -> List[str]:
        """Transcribe a buffer of 16kHz float32 audio.

        Filters short buffers (< min_chunk_duration_s) to avoid hallucination.
        Filters segments with high no_speech_prob to reject hallucinations on silence.

        Args:
            audio_16k: numpy float32 array at 16000 Hz, values in [-1.0, 1.0]

        Returns:
            List of transcribed text segments, filtered for quality.
        """
        if self._model is None:
            raise RuntimeError("STTEngine not initialized. Call initialize() first.")

        # Pitfall 5: skip very short buffers — Whisper hallucinates on < 500ms audio
        if len(audio_16k) / 16000 < self.config.min_chunk_duration_s:
            return []

        loop = asyncio.get_event_loop()

        def _transcribe():
            segments, _info = self._model.transcribe(
                audio_16k,
                language=self.config.language,
                vad_filter=self.config.vad_filter,
                vad_parameters={
                    "min_silence_duration_ms": self.config.vad_min_silence_ms,
                    "threshold": self.config.vad_threshold,
                },
            )
            results = []
            for segment in segments:
                # Pitfall 5: reject segments with high no_speech_prob (hallucinations)
                if segment.no_speech_prob > self.config.no_speech_prob_threshold:
                    logger.debug(
                        "stt.rejected_segment",
                        text=segment.text[:50],
                        no_speech_prob=segment.no_speech_prob,
                    )
                    continue
                text = segment.text.strip()
                if text:
                    results.append(text)
            return results

        return await loop.run_in_executor(None, _transcribe)
