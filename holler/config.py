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
class PoolConfig:
    """Configuration for the DID number pool.

    Per D-01, D-02: Pool stored in Redis SET, initialized from config-defined
    list of DIDs.
    """
    redis_url: str = "redis://localhost:6379"
    pool_key: str = "holler:did_pool"
    dids: str = ""  # Comma-separated E.164 DIDs, or empty (populate manually)


@dataclass
class ComplianceConfig:
    """Configuration for the compliance gateway and country modules.

    Per D-07, D-08: Compliance gateway is mandatory in the outbound call path.
    Per D-14: Consent records stored in SQLite (append-only).
    Per D-20, D-21: Audit log written as append-only JSONL + SQLite index.
    """
    consent_db_path: str = "./data/consent.db"
    dnc_db_path: str = "./data/dnc.db"
    audit_log_dir: str = "./data/audit"
    audit_db_path: str = "./data/audit.db"
    check_timeout_s: float = 2.0
    opt_out_dtmf_key: str = "9"
    opt_out_keywords: str = "stop,remove me,do not call"


@dataclass
class RecordingConfig:
    """Configuration for call recording and post-call transcription.

    Per D-17: Recording via FreeSWITCH uuid_record ESL command.
    Per D-18: Post-call transcript via faster-whisper (background task).
    """
    enabled: bool = True
    recordings_dir: str = "./recordings"
    sample_rate: int = 8000
    transcript_enabled: bool = True
    transcript_device: str = "cpu"
    transcript_compute_type: str = "int8"


@dataclass
class HollerConfig:
    """Top-level configuration assembled from environment."""
    esl: ESLConfig
    stt: STTConfig
    tts: TTSConfig
    llm: LLMConfig
    vad: VADConfig
    audio_bridge: AudioBridgeConfig
    pool: PoolConfig
    compliance: ComplianceConfig
    recording: RecordingConfig

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
            pool=PoolConfig(
                redis_url=os.getenv("HOLLER_REDIS_URL", "redis://localhost:6379"),
                pool_key=os.getenv("HOLLER_POOL_KEY", "holler:did_pool"),
                dids=os.getenv("HOLLER_POOL_DIDS", ""),
            ),
            compliance=ComplianceConfig(
                consent_db_path=os.getenv("HOLLER_CONSENT_DB", "./data/consent.db"),
                dnc_db_path=os.getenv("HOLLER_DNC_DB", "./data/dnc.db"),
                audit_log_dir=os.getenv("HOLLER_AUDIT_LOG_DIR", "./data/audit"),
                audit_db_path=os.getenv("HOLLER_AUDIT_DB", "./data/audit.db"),
                check_timeout_s=float(os.getenv("HOLLER_COMPLIANCE_TIMEOUT", "2.0")),
                opt_out_dtmf_key=os.getenv("HOLLER_OPT_OUT_DTMF", "9"),
                opt_out_keywords=os.getenv("HOLLER_OPT_OUT_KEYWORDS", "stop,remove me,do not call"),
            ),
            recording=RecordingConfig(
                enabled=os.getenv("HOLLER_RECORDING_ENABLED", "true").lower() == "true",
                recordings_dir=os.getenv("HOLLER_RECORDINGS_DIR", "./recordings"),
                sample_rate=int(os.getenv("HOLLER_RECORDING_SAMPLE_RATE", "8000")),
                transcript_enabled=os.getenv("HOLLER_TRANSCRIPT_ENABLED", "true").lower() == "true",
                transcript_device=os.getenv("HOLLER_TRANSCRIPT_DEVICE", "cpu"),
                transcript_compute_type=os.getenv("HOLLER_TRANSCRIPT_COMPUTE_TYPE", "int8"),
            ),
        )
