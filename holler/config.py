"""Centralized configuration for Holler.

Reads from environment variables with sensible defaults.
All config objects for subcomponents are derived here.
"""
import os
from dataclasses import dataclass

from holler.core.freeswitch.esl import ESLConfig
from holler.core.voice.stt import STTConfig
from holler.core.voice.tts import TTSConfig
from holler.core.voice.llm import LLMConfig
from holler.core.voice.vad import VADConfig
from holler.core.voice.audio_bridge import AudioBridgeConfig


@dataclass
class HollerConfig:
    """Top-level configuration assembled from environment."""
    esl: ESLConfig
    stt: STTConfig
    tts: TTSConfig
    llm: LLMConfig
    vad: VADConfig
    audio_bridge: AudioBridgeConfig

    @classmethod
    def from_env(cls) -> "HollerConfig":
        return cls(
            esl=ESLConfig(
                host=os.getenv("ESL_HOST", "127.0.0.1"),
                port=int(os.getenv("ESL_PORT", "8021")),
                password=os.getenv("ESL_PASSWORD", "ClueCon"),
                audio_stream_ws_base=os.getenv("AUDIO_STREAM_WS_BASE", "ws://127.0.0.1:8765/voice"),
            ),
            stt=STTConfig(
                model_name=os.getenv("WHISPER_MODEL", "distil-large-v3"),
                device=os.getenv("WHISPER_DEVICE", "cpu"),
                compute_type=os.getenv("WHISPER_COMPUTE_TYPE", "int8"),
                language=os.getenv("WHISPER_LANGUAGE", "en"),
            ),
            tts=TTSConfig(
                model_path=os.getenv("KOKORO_MODEL_PATH", "kokoro-v1.0.onnx"),
                voices_path=os.getenv("KOKORO_VOICES_PATH", "voices-v1.0.bin"),
                voice=os.getenv("KOKORO_VOICE", "af_sarah"),
            ),
            llm=LLMConfig(
                base_url=os.getenv("LLM_BASE_URL", "http://localhost:11434/v1"),
                api_key=os.getenv("LLM_API_KEY", "ollama"),
                model=os.getenv("LLM_MODEL", "llama3.2"),
            ),
            vad=VADConfig(
                silence_threshold_ms=float(os.getenv("VAD_SILENCE_THRESHOLD_MS", "700")),
                barge_in_grace_ms=float(os.getenv("VAD_BARGE_IN_GRACE_MS", "500")),
            ),
            audio_bridge=AudioBridgeConfig(
                host=os.getenv("AUDIO_BRIDGE_HOST", "0.0.0.0"),
                port=int(os.getenv("AUDIO_BRIDGE_PORT", "8765")),
            ),
        )
