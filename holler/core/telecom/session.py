"""Telecom session state.

TelecomSession wraps VoiceSession via composition (not inheritance) and carries
the full telecom context: DID, destination, jurisdiction, compliance state,
recording paths, and call lifecycle timestamps.

Per D-05 (CONTEXT.md): TelecomSession adds DID allocation, compliance state,
recording reference, and jurisdiction context. VoiceSession remains
voice-pipeline-only.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from holler.core.voice.pipeline import VoiceSession
from holler.core.compliance.gateway import ComplianceResult


@dataclass
class TelecomSession:
    """Per-call telecom session state.

    This is the single source of truth for the call lifecycle (D-06). All
    components (compliance gateway, recording, audit log) read/write through
    this object.

    The voice_session field is Optional because TelecomSession is created at
    call initiation time (before the voice pipeline connects). The
    voice_session is set when the call is answered and the audio bridge
    connects.
    """

    # Core call identifiers
    session_uuid: str
    call_uuid: str

    # Telecom context
    did: str               # Checked-out DID for this call (from NumberPool)
    destination: str       # E.164 destination number
    jurisdiction: str      # e.g. "us", "uk" — resolved by jurisdiction router

    # Voice pipeline composition (D-05: composition, not inheritance)
    voice_session: Optional[VoiceSession] = None

    # Compliance state
    compliance_result: Optional[ComplianceResult] = None

    # Consent / opt-out state machine (D-14, D-15, D-16)
    # Values: "consented", "opted_out", "unknown"
    consent_status: str = "unknown"

    # Recording and transcript paths (D-17, D-18, D-19)
    recording_path: Optional[str] = None
    transcript_path: Optional[str] = None

    # Call lifecycle timestamps (Unix epoch float)
    started_at: Optional[float] = None    # Call attempt initiated
    answered_at: Optional[float] = None  # Call connected (ANSWER event)
    ended_at: Optional[float] = None     # Call terminated (HANGUP event)
