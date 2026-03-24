"""Tests for compliance types and telecom session contracts.

Tests ComplianceResult dataclass, ComplianceModule ABC,
TelecomSession dataclass, and exception types.
"""
import asyncio
import pytest

from holler.core.compliance.gateway import (
    ComplianceResult,
    ComplianceModule,
    ComplianceBlockError,
    NoComplianceModuleError,
)
from holler.core.telecom.session import TelecomSession
from holler.core.voice.pipeline import VoiceSession


# ---------------------------------------------------------------------------
# ComplianceResult tests
# ---------------------------------------------------------------------------

def test_compliance_result_passed():
    """ComplianceResult with passed=True constructs correctly."""
    result = ComplianceResult(
        passed=True,
        reason="ok",
        check_type="tcpa",
        audit_fields={},
    )
    assert result.passed is True
    assert result.reason == "ok"
    assert result.check_type == "tcpa"
    assert result.audit_fields == {}


def test_compliance_result_failed():
    """ComplianceResult with passed=False carries failure state."""
    result = ComplianceResult(
        passed=False,
        reason="dnc_match",
        check_type="dnc",
        audit_fields={"number": "+15550001234"},
    )
    assert result.passed is False
    assert result.reason == "dnc_match"
    assert result.check_type == "dnc"
    assert result.audit_fields == {"number": "+15550001234"}


# ---------------------------------------------------------------------------
# ComplianceModule ABC tests
# ---------------------------------------------------------------------------

def test_compliance_module_abstract_cannot_instantiate():
    """ComplianceModule ABC cannot be instantiated directly."""
    with pytest.raises(TypeError):
        ComplianceModule()


def test_compliance_module_concrete_subclass():
    """A concrete subclass implementing check_outbound() can be instantiated and called."""

    class DummyModule(ComplianceModule):
        async def check_outbound(self, destination: str, session) -> ComplianceResult:
            return ComplianceResult(
                passed=True,
                reason="dummy_allow",
                check_type="dummy",
                audit_fields={"destination": destination},
            )

    module = DummyModule()
    assert module is not None

    result = asyncio.get_event_loop().run_until_complete(
        module.check_outbound("+15550001234", None)
    )
    assert result.passed is True
    assert result.check_type == "dummy"


# ---------------------------------------------------------------------------
# TelecomSession tests
# ---------------------------------------------------------------------------

def test_telecom_session_construction_with_voice_session():
    """TelecomSession can be constructed with voice_session=VoiceSession."""
    voice = VoiceSession(call_uuid="call-123", session_uuid="sess-123")
    ts = TelecomSession(
        session_uuid="sess-123",
        call_uuid="call-123",
        did="+15550009999",
        destination="+15550001234",
        jurisdiction="us",
        voice_session=voice,
    )
    assert ts.voice_session is voice
    assert ts.voice_session.call_uuid == "call-123"


def test_telecom_session_default_consent_status():
    """TelecomSession default consent_status is 'unknown'."""
    ts = TelecomSession(
        session_uuid="sess-456",
        call_uuid="call-456",
        did="+15550009998",
        destination="+15550005678",
        jurisdiction="us",
    )
    assert ts.consent_status == "unknown"


def test_telecom_session_optional_fields_default_none():
    """TelecomSession optional fields default to None."""
    ts = TelecomSession(
        session_uuid="sess-789",
        call_uuid="call-789",
        did="+15550009997",
        destination="+15550009876",
        jurisdiction="uk",
    )
    assert ts.voice_session is None
    assert ts.compliance_result is None
    assert ts.recording_path is None
    assert ts.transcript_path is None
    assert ts.started_at is None
    assert ts.answered_at is None
    assert ts.ended_at is None


# ---------------------------------------------------------------------------
# Exception type tests
# ---------------------------------------------------------------------------

def test_compliance_block_error_raiseable():
    """ComplianceBlockError is raiseable with a message string."""
    with pytest.raises(ComplianceBlockError) as exc_info:
        raise ComplianceBlockError("DNC match for +15550001234")
    assert "DNC match" in str(exc_info.value)


def test_no_compliance_module_error_raiseable():
    """NoComplianceModuleError is raiseable with a message string."""
    with pytest.raises(NoComplianceModuleError) as exc_info:
        raise NoComplianceModuleError("No compliance module for jurisdiction: zz")
    assert "zz" in str(exc_info.value)
