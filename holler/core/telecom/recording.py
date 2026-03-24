"""Call recording and post-call transcription.

Provides thin wrappers around FreeSWITCH uuid_record ESL commands for
call recording start/stop, and async post-call transcription via faster-whisper.

Per D-17: Recording via FreeSWITCH uuid_record ESL command.
Per D-18: Post-call transcript via faster-whisper (background task after hangup).
Per D-19: Recording WAV and transcript JSON stored in configurable directory
          with date-based subdirectories.

Design decisions:
- Module-level functions (not a class) — these are thin wrappers around ESL commands.
- transcribe_recording() uses run_in_executor because faster-whisper transcribe()
  is CPU-bound (Research Pattern 7). The model is a separate CPU-only instance —
  NOT the live STT model (Pitfall 6).
- stop_recording() sends explicit stop command — do NOT rely on RECORD_STOP event
  (Pitfall 1 from research).
"""
from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from holler.core.freeswitch.esl import FreeSwitchESL


def recording_path(recordings_dir: str, call_uuid: str) -> str:
    """Generate recording file path: {dir}/{YYYY-MM-DD}/{call_uuid}.wav

    Creates the date-based subdirectory if it does not exist.

    Args:
        recordings_dir: Base directory for recordings (e.g. "./recordings").
        call_uuid: FreeSWITCH call UUID for the recording filename.

    Returns:
        Absolute path string for the WAV file.
    """
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = Path(recordings_dir) / date_str / f"{call_uuid}.wav"
    path.parent.mkdir(parents=True, exist_ok=True)
    return str(path)


async def start_recording(esl: "FreeSwitchESL", call_uuid: str, path: str) -> None:
    """Start recording via uuid_record. Set sample rate first (8kHz per D-17).

    Sends two ESL commands:
    1. uuid_setvar to set the recording sample rate to 8kHz
    2. uuid_record start to begin capturing audio to the given path

    Args:
        esl: FreeSwitchESL client for sending commands.
        call_uuid: FreeSWITCH call UUID to record.
        path: Local filesystem path for the WAV file (from recording_path()).
    """
    await esl.send_raw(f"api uuid_setvar {call_uuid} record_sample_rate 8000")
    await esl.send_raw(f"api uuid_record {call_uuid} start {path}")


async def stop_recording(esl: "FreeSwitchESL", call_uuid: str, path: str) -> None:
    """Stop recording explicitly via uuid_record stop.

    Do NOT rely on RECORD_STOP event (Pitfall 1 from research) — send explicit
    stop command on hangup to ensure recording is finalized.

    Args:
        esl: FreeSwitchESL client for sending commands.
        call_uuid: FreeSWITCH call UUID to stop recording.
        path: Local filesystem path for the WAV file (must match start_recording path).
    """
    await esl.send_raw(f"api uuid_record {call_uuid} stop {path}")


async def transcribe_recording(wav_path: str, model) -> str:
    """Run post-call transcription in executor thread. Returns transcript JSON path.

    Uses run_in_executor because faster-whisper transcribe() is CPU-bound
    (Research Pattern 7). The model should be a separate CPU-only instance —
    NOT the live STT model (Pitfall 6).

    The transcript JSON is written alongside the WAV file with a
    .transcript.json suffix.

    Args:
        wav_path: Path to the WAV recording file.
        model: A faster-whisper WhisperModel instance (CPU, int8 recommended).
               Must NOT be the same instance used for live STT.

    Returns:
        Path string to the generated .transcript.json file.
    """
    loop = asyncio.get_event_loop()

    def _transcribe():
        segments, info = model.transcribe(wav_path, beam_size=5)
        return [
            {"start": s.start, "end": s.end, "text": s.text}
            for s in segments
        ], info

    segments, info = await loop.run_in_executor(None, _transcribe)

    json_path = wav_path.replace(".wav", ".transcript.json")
    with open(json_path, "w") as f:
        json.dump(
            {
                "segments": segments,
                "language": getattr(info, "language", "en"),
            },
            f,
            indent=2,
        )
    return json_path
