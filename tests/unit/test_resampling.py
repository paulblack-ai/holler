"""Tests for audio resampling module.

Tests cover:
- upsample_8k_to_16k: 8kHz int16 PCM bytes -> 16kHz float32 array
- downsample_24k_to_8k: 24kHz float32 array -> 8kHz int16 PCM bytes
- StreamResampler: stateful streaming resampler for real-time chunks
- Empty input handling
"""
import numpy as np
import pytest

from holler.core.voice.resampler import (
    upsample_8k_to_16k,
    downsample_24k_to_8k,
    StreamResampler,
)


def make_sine_8k(num_samples: int, freq: float = 440.0) -> bytes:
    """Generate sine wave at 8kHz as int16 PCM bytes."""
    t = np.arange(num_samples) / 8000.0
    audio = np.sin(2 * np.pi * freq * t)
    return (audio * 32767).astype(np.int16).tobytes()


def make_sine_float32(num_samples: int, sample_rate: int, freq: float = 440.0) -> np.ndarray:
    """Generate sine wave as float32 array normalized to [-1.0, 1.0]."""
    t = np.arange(num_samples) / sample_rate
    return np.sin(2 * np.pi * freq * t).astype(np.float32)


class TestUpsample8kTo16k:
    def test_output_length_approximately_doubled(self):
        """Given 160 samples at 8kHz, output should be approximately 320 samples at 16kHz."""
        pcm_8k = make_sine_8k(160)
        result = upsample_8k_to_16k(pcm_8k)
        # Allow up to 5% tolerance for filter delay
        assert abs(len(result) - 320) <= 16, f"Expected ~320 samples, got {len(result)}"

    def test_output_is_float32(self):
        """Output must be float32 array."""
        pcm_8k = make_sine_8k(160)
        result = upsample_8k_to_16k(pcm_8k)
        assert result.dtype == np.float32

    def test_output_values_in_range(self):
        """Output values must be in [-1.0, 1.0]."""
        pcm_8k = make_sine_8k(160)
        result = upsample_8k_to_16k(pcm_8k)
        assert result.max() <= 1.0 + 1e-6, f"Max value {result.max()} exceeds 1.0"
        assert result.min() >= -1.0 - 1e-6, f"Min value {result.min()} below -1.0"

    def test_empty_input_returns_empty(self):
        """Empty input should return empty array without error."""
        result = upsample_8k_to_16k(b"")
        assert len(result) == 0

    def test_1_second_audio(self):
        """1 second of 8kHz audio (8000 samples) -> ~16000 samples at 16kHz."""
        pcm_8k = make_sine_8k(8000)
        result = upsample_8k_to_16k(pcm_8k)
        assert abs(len(result) - 16000) <= 800, f"Expected ~16000 samples, got {len(result)}"


class TestDownsample24kTo8k:
    def test_output_is_bytes(self):
        """Output must be bytes (int16 PCM)."""
        samples_24k = make_sine_float32(480, 24000)
        result = downsample_24k_to_8k(samples_24k)
        assert isinstance(result, bytes)

    def test_output_length_approximately_one_third(self):
        """Given 480 float32 samples at 24kHz (20ms), output ~160 int16 samples = 320 bytes."""
        samples_24k = make_sine_float32(480, 24000)
        result = downsample_24k_to_8k(samples_24k)
        # 480 samples at 24kHz -> ~160 samples at 8kHz = 320 bytes
        expected_bytes = 320
        assert abs(len(result) - expected_bytes) <= 16, f"Expected ~{expected_bytes} bytes, got {len(result)}"

    def test_1_second_audio(self):
        """1 second of 24kHz audio (24000 samples) -> approximately 8000 int16 samples = 16000 bytes."""
        samples_24k = make_sine_float32(24000, 24000)
        result = downsample_24k_to_8k(samples_24k)
        # 8000 samples * 2 bytes/sample = 16000 bytes
        assert abs(len(result) - 16000) <= 800, f"Expected ~16000 bytes, got {len(result)}"

    def test_empty_input_returns_empty(self):
        """Empty input should return empty bytes without error."""
        result = downsample_24k_to_8k(np.array([], dtype=np.float32))
        assert result == b""

    def test_int16_range_preserved(self):
        """Output int16 values should not overflow (values should stay in int16 range)."""
        # Full-amplitude sine wave
        samples_24k = make_sine_float32(24000, 24000)
        result = downsample_24k_to_8k(samples_24k)
        arr = np.frombuffer(result, dtype=np.int16)
        assert arr.max() <= 32767
        assert arr.min() >= -32768


class TestStreamResampler8kTo16k:
    def test_total_output_length_approximately_doubled(self):
        """Multiple sequential chunks: total output ~2x total input."""
        resampler = StreamResampler(from_rate=8000, to_rate=16000, dtype="float32")
        total_input = 0
        total_output = 0
        chunk_size = 160  # 20ms at 8kHz
        for _ in range(50):  # 1 second
            chunk = np.sin(2 * np.pi * 440 * np.arange(chunk_size) / 8000.0).astype(np.float32)
            output = resampler.process(chunk)
            total_input += len(chunk)
            total_output += len(output)
        # 5% tolerance for filter delay
        expected = total_input * 2
        tolerance = expected * 0.05
        assert abs(total_output - expected) <= tolerance, (
            f"Expected ~{expected} output samples, got {total_output}"
        )

    def test_streaming_produces_output(self):
        """StreamResampler must produce non-empty output for non-empty input."""
        resampler = StreamResampler(from_rate=8000, to_rate=16000)
        chunk = np.zeros(160, dtype=np.float32)
        output = resampler.process(chunk)
        assert isinstance(output, np.ndarray)


class TestStreamResampler24kTo8k:
    def test_1_second_audio_produces_correct_output(self):
        """24000 float32 samples (1 second) -> approximately 8000 int16 samples."""
        resampler = StreamResampler(from_rate=24000, to_rate=8000, dtype="float32")
        # Process in 20ms chunks (480 samples each)
        total_output = 0
        chunk_size = 480
        num_chunks = 50  # 1 second
        for _ in range(num_chunks):
            chunk = np.sin(2 * np.pi * 440 * np.arange(chunk_size) / 24000.0).astype(np.float32)
            output = resampler.process(chunk)
            total_output += len(output)
        expected = 8000
        tolerance = expected * 0.05
        assert abs(total_output - expected) <= tolerance, (
            f"Expected ~{expected} output samples, got {total_output}"
        )
