"""Audio resampling for the voice pipeline.

Handles conversions between:
- 8kHz int16 (PSTN/FreeSWITCH) -> 16kHz float32 (Whisper STT input)
- 24kHz float32 (Kokoro TTS output) -> 8kHz int16 (FreeSWITCH playback)

Uses soxr (SoX resampler) for high-quality conversion. Falls back to
scipy.signal.resample_poly if soxr is unavailable.
"""
import math

import numpy as np

try:
    import soxr
    HAS_SOXR = True
except ImportError:
    HAS_SOXR = False


def upsample_8k_to_16k(pcm_8k: bytes) -> np.ndarray:
    """Convert 8kHz int16 PCM bytes to 16kHz float32 array for Whisper.

    Args:
        pcm_8k: Raw PCM bytes, int16, 8000 Hz
    Returns:
        numpy float32 array at 16000 Hz, values in [-1.0, 1.0]
    """
    if len(pcm_8k) == 0:
        return np.array([], dtype=np.float32)

    audio = np.frombuffer(pcm_8k, dtype=np.int16).astype(np.float32) / 32768.0

    if HAS_SOXR:
        resampled = soxr.resample(audio, 8000, 16000, quality="HQ")
    else:
        from scipy.signal import resample_poly
        gcd = math.gcd(16000, 8000)
        up = 16000 // gcd
        down = 8000 // gcd
        resampled = resample_poly(audio, up, down).astype(np.float32)

    # Clamp to [-1.0, 1.0] to handle slight overshoot from resampler ringing
    return np.clip(resampled, -1.0, 1.0).astype(np.float32)


def downsample_24k_to_8k(samples: np.ndarray) -> bytes:
    """Convert 24kHz float32 array from Kokoro to 8kHz int16 PCM bytes for FreeSWITCH.

    Args:
        samples: numpy float32 array at 24000 Hz, values in [-1.0, 1.0]
    Returns:
        Raw PCM bytes, int16, 8000 Hz
    """
    if len(samples) == 0:
        return b""

    if HAS_SOXR:
        resampled = soxr.resample(samples, 24000, 8000, quality="HQ")
    else:
        from scipy.signal import resample_poly
        gcd = math.gcd(8000, 24000)
        up = 8000 // gcd
        down = 24000 // gcd
        resampled = resample_poly(samples, up, down)

    # Clamp to [-1.0, 1.0] to prevent int16 overflow
    resampled = np.clip(resampled, -1.0, 1.0)
    return (resampled * 32767).astype(np.int16).tobytes()


class StreamResampler:
    """Stateful resampler for real-time chunked audio processing.

    Uses soxr.ResampleStream for phase-continuous resampling across chunks,
    ensuring correct output at chunk boundaries without phase discontinuities.

    Falls back to scipy.signal.resample_poly per-chunk if soxr is unavailable
    (note: scipy fallback does not maintain state across chunks).
    """

    def __init__(self, from_rate: int, to_rate: int, dtype: str = "float32"):
        self._from_rate = from_rate
        self._to_rate = to_rate
        self._dtype = dtype
        if HAS_SOXR:
            self._resampler = soxr.ResampleStream(
                from_rate, to_rate, 1, dtype=dtype, quality="HQ"
            )
        else:
            self._resampler = None
            # Compute up/down ratios for scipy fallback
            gcd = math.gcd(to_rate, from_rate)
            self._up = to_rate // gcd
            self._down = from_rate // gcd

    def process(self, chunk: np.ndarray) -> np.ndarray:
        """Resample a chunk of audio, maintaining state across calls.

        Args:
            chunk: Input audio samples as numpy array
        Returns:
            Resampled audio samples as numpy array
        """
        if len(chunk) == 0:
            return np.array([], dtype=np.float32)

        if HAS_SOXR:
            return self._resampler.resample_chunk(chunk)
        else:
            from scipy.signal import resample_poly
            return resample_poly(chunk.astype(np.float32), self._up, self._down).astype(np.float32)
