"""Tests for ComplianceGateway — mandatory pre-originate compliance gate.

Tests cover:
- compliance check runs BEFORE esl.originate()
- passed=True allows call, returns call_uuid
- passed=False blocks call, releases DID, raises ComplianceBlockError
- audit log written on every path (pass or fail)
- exception in check_outbound is fail-closed
- timeout in check_outbound is fail-closed
- audit log entry contains required fields
"""
from __future__ import annotations

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, call, patch

from holler.core.compliance.gateway import (
    ComplianceBlockError,
    ComplianceGateway,
    ComplianceModule,
    ComplianceResult,
    NoComplianceModuleError,
)
from holler.core.telecom.session import TelecomSession


# ---------------------------------------------------------------------------
# Test fixtures / stubs
# ---------------------------------------------------------------------------

def make_session(**overrides) -> TelecomSession:
    """Factory for a minimal TelecomSession."""
    from holler.core.voice.pipeline import VoiceSession
    defaults = dict(
        session_uuid="sess-001",
        call_uuid="call-001",
        did="+15550001234",
        destination="+14155559999",
        jurisdiction="us",
    )
    defaults.update(overrides)
    # Build without voice_session (optional field)
    return TelecomSession(**defaults)


class StubComplianceModule(ComplianceModule):
    """Configurable stub that returns a preset ComplianceResult."""

    def __init__(self, result: ComplianceResult, delay: float = 0.0):
        self._result = result
        self._delay = delay
        self.call_count = 0

    async def check_outbound(self, destination: str, session: TelecomSession) -> ComplianceResult:
        self.call_count += 1
        if self._delay:
            await asyncio.sleep(self._delay)
        return self._result


class RaisingComplianceModule(ComplianceModule):
    """Stub that raises an exception on check."""

    def __init__(self, exc: Exception):
        self._exc = exc

    async def check_outbound(self, destination: str, session: TelecomSession) -> ComplianceResult:
        raise self._exc


class StubRouter:
    """Minimal router stub that returns a fixed module."""

    def __init__(self, module: ComplianceModule = None, raise_no_module: bool = False):
        self._module = module
        self._raise = raise_no_module

    def resolve(self, destination: str) -> ComplianceModule:
        if self._raise:
            raise NoComplianceModuleError(f"No module for {destination}")
        return self._module


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def run(coro):
    """Run a coroutine in a fresh event loop (no pytest-asyncio needed)."""
    return asyncio.get_event_loop().run_until_complete(coro)


def make_esl(call_uuid: str = "esl-call-uuid-001") -> AsyncMock:
    esl = AsyncMock()
    esl.originate = AsyncMock(return_value=call_uuid)
    return esl


def make_pool() -> AsyncMock:
    pool = AsyncMock()
    pool.release = AsyncMock()
    return pool


def make_audit() -> AsyncMock:
    audit = AsyncMock()
    audit.write = AsyncMock()
    return audit


# ---------------------------------------------------------------------------
# Test: originate_checked calls compliance module BEFORE esl.originate
# ---------------------------------------------------------------------------

def test_compliance_check_runs_before_originate():
    """check_outbound must be called before esl.originate()."""
    call_order = []

    class TrackingModule(ComplianceModule):
        async def check_outbound(self, destination, session):
            call_order.append("check")
            return ComplianceResult(passed=True, reason="ok", check_type="stub")

    esl = AsyncMock()
    async def mock_originate(*args, **kwargs):
        call_order.append("originate")
        return "uuid-001"
    esl.originate = mock_originate

    pool = make_pool()
    audit = make_audit()
    router = StubRouter(TrackingModule())

    gateway = ComplianceGateway(router=router, audit_log=audit)
    session = make_session()

    run(gateway.originate_checked(esl, pool, session))

    assert call_order == ["check", "originate"], (
        f"check must precede originate, got order: {call_order}"
    )


# ---------------------------------------------------------------------------
# Test: passed=True — originate IS called, returns call_uuid
# ---------------------------------------------------------------------------

def test_passed_compliance_calls_originate_and_returns_uuid():
    """When check_outbound returns passed=True, originate() must be called and call_uuid returned."""
    pass_result = ComplianceResult(passed=True, reason="allowed", check_type="tcpa")
    router = StubRouter(StubComplianceModule(pass_result))
    esl = make_esl("esl-call-abc")
    pool = make_pool()
    audit = make_audit()

    gateway = ComplianceGateway(router=router, audit_log=audit)
    session = make_session()

    returned_uuid = run(gateway.originate_checked(esl, pool, session))

    esl.originate.assert_awaited_once()
    assert returned_uuid == "esl-call-abc"


# ---------------------------------------------------------------------------
# Test: passed=False — originate NOT called, DID released, ComplianceBlockError raised
# ---------------------------------------------------------------------------

def test_failed_compliance_blocks_call_releases_did_raises_error():
    """When check_outbound returns passed=False:
    - esl.originate() must NOT be called
    - pool.release() must be called with the DID
    - ComplianceBlockError must be raised
    """
    deny_result = ComplianceResult(passed=False, reason="dnc_match", check_type="dnc")
    router = StubRouter(StubComplianceModule(deny_result))
    esl = make_esl()
    pool = make_pool()
    audit = make_audit()

    gateway = ComplianceGateway(router=router, audit_log=audit)
    session = make_session(did="+15550009876")

    with pytest.raises(ComplianceBlockError):
        run(gateway.originate_checked(esl, pool, session))

    esl.originate.assert_not_awaited()
    pool.release.assert_awaited_once_with("+15550009876")


# ---------------------------------------------------------------------------
# Test: audit log written on pass
# ---------------------------------------------------------------------------

def test_audit_written_on_pass():
    """audit.write() must be called even when compliance passes."""
    pass_result = ComplianceResult(passed=True, reason="ok", check_type="tcpa")
    router = StubRouter(StubComplianceModule(pass_result))
    audit = make_audit()

    gateway = ComplianceGateway(router=router, audit_log=audit)
    session = make_session()

    run(gateway.originate_checked(make_esl(), make_pool(), session))

    audit.write.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test: audit log written on fail
# ---------------------------------------------------------------------------

def test_audit_written_on_fail():
    """audit.write() must be called when compliance denies the call."""
    deny_result = ComplianceResult(passed=False, reason="opt_out", check_type="consent")
    router = StubRouter(StubComplianceModule(deny_result))
    audit = make_audit()

    gateway = ComplianceGateway(router=router, audit_log=audit)
    session = make_session()

    with pytest.raises(ComplianceBlockError):
        run(gateway.originate_checked(make_esl(), make_pool(), session))

    audit.write.assert_awaited_once()


# ---------------------------------------------------------------------------
# Test: exception in check_outbound is fail-closed
# ---------------------------------------------------------------------------

def test_exception_in_check_is_fail_closed():
    """If check_outbound() raises any exception, the call must be blocked (fail-closed)."""
    router = StubRouter(RaisingComplianceModule(RuntimeError("DB connection failed")))
    esl = make_esl()
    pool = make_pool()
    audit = make_audit()

    gateway = ComplianceGateway(router=router, audit_log=audit)
    session = make_session()

    with pytest.raises(ComplianceBlockError) as exc_info:
        run(gateway.originate_checked(esl, pool, session))

    esl.originate.assert_not_awaited()
    assert "compliance_check_error" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Test: timeout in check_outbound is fail-closed
# ---------------------------------------------------------------------------

def test_timeout_in_check_is_fail_closed():
    """If check_outbound() exceeds timeout, the call must be blocked (fail-closed)."""
    # 5s delay, 0.05s timeout — guaranteed to timeout
    slow_module = StubComplianceModule(
        ComplianceResult(passed=True, reason="ok", check_type="stub"),
        delay=5.0,
    )
    router = StubRouter(slow_module)
    esl = make_esl()
    pool = make_pool()
    audit = make_audit()

    gateway = ComplianceGateway(router=router, audit_log=audit, timeout=0.05)
    session = make_session()

    with pytest.raises(ComplianceBlockError) as exc_info:
        run(gateway.originate_checked(esl, pool, session))

    esl.originate.assert_not_awaited()
    assert "timeout" in str(exc_info.value).lower()


# ---------------------------------------------------------------------------
# Test: audit log entry contains required fields
# ---------------------------------------------------------------------------

def test_audit_entry_contains_required_fields():
    """Audit log entry must include: call_uuid, session_uuid, check_type, destination, result, reason, did."""
    pass_result = ComplianceResult(
        passed=True,
        reason="allowed",
        check_type="tcpa",
        audit_fields={"consent_id": "c-001"},
    )
    router = StubRouter(StubComplianceModule(pass_result))
    audit = make_audit()

    gateway = ComplianceGateway(router=router, audit_log=audit)
    session = make_session(
        session_uuid="sess-999",
        call_uuid="call-888",
        did="+15550001111",
        destination="+14155552222",
    )

    run(gateway.originate_checked(make_esl(), make_pool(), session))

    assert audit.write.await_count == 1
    entry = audit.write.call_args[0][0]

    assert entry["call_uuid"] == "call-888"
    assert entry["session_uuid"] == "sess-999"
    assert entry["check_type"] == "tcpa"
    assert entry["destination"] == "+14155552222"
    assert entry["result"] == "allow"
    assert entry["reason"] == "allowed"
    assert entry["did"] == "+15550001111"
    # Extra audit_fields should be merged in
    assert entry["consent_id"] == "c-001"


# ---------------------------------------------------------------------------
# Test: no compliance module (fail-closed)
# ---------------------------------------------------------------------------

def test_no_compliance_module_is_fail_closed():
    """If no module is registered for the destination, call must be denied."""
    router = StubRouter(raise_no_module=True)
    esl = make_esl()
    pool = make_pool()
    audit = make_audit()

    gateway = ComplianceGateway(router=router, audit_log=audit)
    session = make_session(destination="+8613800138000")

    with pytest.raises(ComplianceBlockError):
        run(gateway.originate_checked(esl, pool, session))

    esl.originate.assert_not_awaited()
    pool.release.assert_awaited_once()

    entry = audit.write.call_args[0][0]
    assert entry["result"] == "deny"
    assert entry["reason"] == "no_compliance_module"
