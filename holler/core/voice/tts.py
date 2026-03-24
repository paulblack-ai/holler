"""Text-to-speech engine wrapping Kokoro-ONNX.

Provides sentence-chunked streaming synthesis (VOICE-02).
Splits LLM output at sentence boundaries and synthesizes each sentence
as it arrives, enabling streaming TTS alongside streaming LLM (D-07).
"""
import asyncio
import re
import time
from dataclasses import dataclass
from typing import AsyncGenerator, Optional, Tuple

import numpy as np
import structlog

logger = structlog.get_logger()

SENTENCE_END = re.compile(r'(?<=[.!?])\s+')


@dataclass
class TTSConfig:
    model_path: str = "kokoro-v1.0.onnx"
    voices_path: str = "voices-v1.0.bin"
    voice: str = "af_sarah"
    speed: float = 1.0
    lang: str = "en-us"
    sample_rate: int = 24000  # Kokoro outputs 24kHz


class TTSEngine:
    """Streaming text-to-speech using Kokoro-ONNX.

    Model loading is deferred to initialize() — call once at startup,
    not per-call. synthesize_stream() consumes a token queue and yields
    audio chunks sentence-by-sentence for low-latency streaming.
    """

    def __init__(self, config: Optional[TTSConfig] = None):
        self.config = config or TTSConfig()
        self._kokoro = None

    async def initialize(self) -> None:
        """Load the Kokoro model. Call once at startup, not per-call."""
        from kokoro_onnx import Kokoro
        loop = asyncio.get_event_loop()
        self._kokoro = await loop.run_in_executor(
            None,
            lambda: Kokoro(self.config.model_path, self.config.voices_path)
        )
        logger.info("tts.initialized", voice=self.config.voice)

    async def synthesize(self, text: str) -> Tuple[np.ndarray, int]:
        """Synthesize a single text string to audio.

        Args:
            text: The text to synthesize.

        Returns:
            Tuple of (samples_float32, sample_rate) where sample_rate is 24000.
        """
        if self._kokoro is None:
            raise RuntimeError("TTSEngine not initialized. Call initialize() first.")

        loop = asyncio.get_event_loop()

        def _create():
            return self._kokoro.create(
                text,
                voice=self.config.voice,
                speed=self.config.speed,
                lang=self.config.lang,
            )

        samples, sr = await loop.run_in_executor(None, _create)
        return samples, sr

    async def synthesize_stream(
        self,
        token_queue: asyncio.Queue,
    ) -> AsyncGenerator[Tuple[np.ndarray, int], None]:
        """Yield audio chunks sentence-by-sentence from a streaming token queue.

        Reads tokens from queue, splits at sentence boundaries, synthesizes
        each complete sentence immediately while buffering the incomplete tail.
        This enables streaming TTS output to begin before the full LLM response
        is available, contributing to sub-800ms end-to-end latency (D-07).

        Args:
            token_queue: asyncio.Queue yielding string tokens. None signals end of input.

        Yields:
            Tuples of (samples_float32, sample_rate) for each synthesized sentence.
        """
        text_buffer = ""

        while True:
            token = await token_queue.get()

            if token is None:
                # Sentinel: end of LLM output
                if text_buffer.strip():
                    t0 = time.monotonic()
                    samples, sr = await self.synthesize(text_buffer.strip())
                    duration_ms = (time.monotonic() - t0) * 1000
                    logger.info(
                        "tts.sentence",
                        text=text_buffer.strip()[:50],
                        duration_ms=round(duration_ms, 1),
                    )
                    yield samples, sr
                break

            text_buffer += token

            # Split at sentence boundaries — keep last fragment as incomplete
            parts = SENTENCE_END.split(text_buffer)
            if len(parts) > 1:
                # All parts except the last are complete sentences
                complete_sentences = parts[:-1]
                text_buffer = parts[-1]

                for sentence in complete_sentences:
                    sentence = sentence.strip()
                    if sentence:
                        t0 = time.monotonic()
                        samples, sr = await self.synthesize(sentence)
                        duration_ms = (time.monotonic() - t0) * 1000
                        logger.info(
                            "tts.sentence",
                            text=sentence[:50],
                            duration_ms=round(duration_ms, 1),
                        )
                        yield samples, sr
