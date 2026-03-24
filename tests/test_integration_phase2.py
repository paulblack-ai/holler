"""Phase 2 integration tests — structural verification.

Tests verify:
- Config loads with all Phase 2 sections (pool, compliance, recording)
- ComplianceGateway, NumberPool, ConsentDB, DNCList, AuditLog can all be instantiated
- USComplianceModule registers with JurisdictionRouter for "+1"
- The import chain works end-to-end (no circular imports)
- check_optout_keywords is importable from holler.core.telecom

These are structural integration tests, not live call tests.
All external dependencies (Redis, FreeSWITCH, databases) are mocked.
"""
from __future__ import annotations

import asyncio
import tempfile
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def run(coro):
    """Run a coroutine in a fresh event loop (no pytest-asyncio needed)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Test: Config loads with all Phase 2 sections
# ---------------------------------------------------------------------------

def test_config_has_pool_section():
    """HollerConfig.from_env() includes PoolConfig."""
    from holler.config import HollerConfig, PoolConfig
    config = HollerConfig.from_env()
    assert isinstance(config.pool, PoolConfig)
    assert hasattr(config.pool, "redis_url")
    assert hasattr(config.pool, "pool_key")
    assert hasattr(config.pool, "dids")


def test_config_has_compliance_section():
    """HollerConfig.from_env() includes ComplianceConfig."""
    from holler.config import HollerConfig, ComplianceConfig
    config = HollerConfig.from_env()
    assert isinstance(config.compliance, ComplianceConfig)
    assert hasattr(config.compliance, "consent_db_path")
    assert hasattr(config.compliance, "dnc_db_path")
    assert hasattr(config.compliance, "audit_log_dir")
    assert hasattr(config.compliance, "check_timeout_s")
    assert hasattr(config.compliance, "opt_out_dtmf_key")
    assert hasattr(config.compliance, "opt_out_keywords")


def test_config_has_recording_section():
    """HollerConfig.from_env() includes RecordingConfig."""
    from holler.config import HollerConfig, RecordingConfig
    config = HollerConfig.from_env()
    assert isinstance(config.recording, RecordingConfig)
    assert hasattr(config.recording, "enabled")
    assert hasattr(config.recording, "recordings_dir")
    assert hasattr(config.recording, "transcript_enabled")


def test_compliance_config_opt_out_defaults():
    """ComplianceConfig has correct defaults for opt-out settings."""
    from holler.config import ComplianceConfig
    config = ComplianceConfig()
    assert config.opt_out_dtmf_key == "9"
    assert "stop" in config.opt_out_keywords
    assert "remove me" in config.opt_out_keywords
    assert "do not call" in config.opt_out_keywords


# ---------------------------------------------------------------------------
# Test: All Phase 2 components can be instantiated
# ---------------------------------------------------------------------------

def test_number_pool_instantiation():
    """NumberPool can be instantiated with a mock Redis client."""
    from holler.core.telecom.pool import NumberPool
    mock_redis = MagicMock()
    pool = NumberPool(mock_redis, pool_key="test:pool")
    assert pool is not None


def test_jurisdiction_router_instantiation():
    """JurisdictionRouter can be instantiated."""
    from holler.core.telecom.router import JurisdictionRouter
    router = JurisdictionRouter()
    assert router is not None


def test_consent_db_instantiation():
    """ConsentDB can be instantiated."""
    from holler.core.compliance.consent_db import ConsentDB
    db = ConsentDB(":memory:")
    assert db is not None


def test_dnc_list_instantiation():
    """DNCList can be instantiated."""
    from holler.core.compliance.dnc import DNCList
    dnc = DNCList(":memory:")
    assert dnc is not None


def test_audit_log_instantiation():
    """AuditLog can be instantiated."""
    from holler.core.compliance.audit import AuditLog
    with tempfile.TemporaryDirectory() as tmpdir:
        audit = AuditLog(tmpdir, ":memory:")
        assert audit is not None


def test_us_compliance_module_instantiation():
    """USComplianceModule can be instantiated with mock deps."""
    from holler.countries.us.module import USComplianceModule
    mock_consent_db = MagicMock()
    mock_dnc_list = MagicMock()
    module = USComplianceModule(consent_db=mock_consent_db, dnc_list=mock_dnc_list)
    assert module is not None


def test_compliance_gateway_instantiation():
    """ComplianceGateway can be instantiated."""
    from holler.core.compliance.gateway import ComplianceGateway
    mock_router = MagicMock()
    mock_audit = MagicMock()
    gateway = ComplianceGateway(router=mock_router, audit_log=mock_audit, timeout=2.0)
    assert gateway is not None


# ---------------------------------------------------------------------------
# Test: USComplianceModule registers with JurisdictionRouter for "+1"
# ---------------------------------------------------------------------------

def test_us_module_registers_for_plus1():
    """USComplianceModule registered for '+1' resolves correctly."""
    from holler.core.telecom.router import JurisdictionRouter
    from holler.countries.us.module import USComplianceModule
    from holler.core.compliance.gateway import ComplianceModule

    router = JurisdictionRouter()
    mock_consent = MagicMock()
    mock_dnc = MagicMock()
    us_module = USComplianceModule(consent_db=mock_consent, dnc_list=mock_dnc)

    router.register("+1", us_module)

    resolved = router.resolve("+14155551234")
    assert resolved is us_module, "Expected USComplianceModule for +1 destination"


def test_us_module_resolves_for_various_us_numbers():
    """JurisdictionRouter with '+1' prefix resolves any US E.164 number."""
    from holler.core.telecom.router import JurisdictionRouter
    from holler.countries.us.module import USComplianceModule

    router = JurisdictionRouter()
    mock_consent = MagicMock()
    mock_dnc = MagicMock()
    us_module = USComplianceModule(consent_db=mock_consent, dnc_list=mock_dnc)
    router.register("+1", us_module)

    # Various US numbers should all resolve to US module
    for number in ["+12125551234", "+14085559876", "+18005551234"]:
        resolved = router.resolve(number)
        assert resolved is us_module, f"Expected USComplianceModule for {number}"


def test_non_us_number_raises_no_module_error():
    """JurisdictionRouter fails closed when no module for destination."""
    from holler.core.telecom.router import JurisdictionRouter
    from holler.core.compliance.gateway import NoComplianceModuleError
    from holler.countries.us.module import USComplianceModule

    router = JurisdictionRouter()
    mock_consent = MagicMock()
    mock_dnc = MagicMock()
    router.register("+1", USComplianceModule(consent_db=mock_consent, dnc_list=mock_dnc))

    with pytest.raises(NoComplianceModuleError):
        router.resolve("+447911123456")  # UK number, no module registered


# ---------------------------------------------------------------------------
# Test: Import chain works end-to-end (no circular imports)
# ---------------------------------------------------------------------------

def test_import_chain_main():
    """main module imports without circular import errors."""
    from holler.main import main
    assert callable(main)


def test_import_chain_telecom_package():
    """holler.core.telecom package imports all expected names."""
    from holler.core.telecom import (
        TelecomSession,
        NumberPool,
        NumberPoolExhaustedError,
        JurisdictionRouter,
        check_optout_keywords,
    )
    assert TelecomSession is not None
    assert NumberPool is not None
    assert NumberPoolExhaustedError is not None
    assert JurisdictionRouter is not None
    assert callable(check_optout_keywords)


def test_import_chain_compliance_package():
    """holler.core.compliance package imports all expected names."""
    from holler.core.compliance import (
        ComplianceModule,
        ComplianceResult,
        ComplianceBlockError,
        NoComplianceModuleError,
    )
    assert ComplianceModule is not None
    assert ComplianceResult is not None
    assert ComplianceBlockError is not None
    assert NoComplianceModuleError is not None


def test_import_chain_recording():
    """holler.core.telecom.recording imports without errors."""
    from holler.core.telecom.recording import (
        recording_path,
        start_recording,
        stop_recording,
        transcribe_recording,
    )
    assert callable(recording_path)
    assert callable(start_recording)
    assert callable(stop_recording)
    assert callable(transcribe_recording)


# ---------------------------------------------------------------------------
# Test: TelecomSession can be created for a call
# ---------------------------------------------------------------------------

def test_telecom_session_creation():
    """TelecomSession can be created with required fields."""
    from holler.core.telecom.session import TelecomSession
    import time

    session = TelecomSession(
        session_uuid="sess-001",
        call_uuid="",
        did="+15550001234",
        destination="+14155559999",
        jurisdiction="us",
        started_at=time.monotonic(),
    )
    assert session.session_uuid == "sess-001"
    assert session.did == "+15550001234"
    assert session.destination == "+14155559999"
    assert session.jurisdiction == "us"
    assert session.voice_session is None
    assert session.compliance_result is None
    assert session.recording_path is None
    assert session.transcript_path is None
    assert session.consent_status == "unknown"


def test_telecom_session_mutable_fields():
    """TelecomSession fields can be updated during call lifecycle."""
    from holler.core.telecom.session import TelecomSession
    import time

    session = TelecomSession(
        session_uuid="sess-002",
        call_uuid="",
        did="+15550001234",
        destination="+14155559999",
        jurisdiction="us",
    )

    # Simulate call lifecycle
    session.call_uuid = "freeswitch-call-uuid-123"
    session.recording_path = "/recordings/2026-03-24/freeswitch-call-uuid-123.wav"
    session.answered_at = time.monotonic()
    session.consent_status = "consented"

    assert session.call_uuid == "freeswitch-call-uuid-123"
    assert session.recording_path is not None
    assert session.answered_at is not None
    assert session.consent_status == "consented"


# ---------------------------------------------------------------------------
# Test: Main module has required integration points
# ---------------------------------------------------------------------------

def test_main_uses_compliance_gateway():
    """main.py imports and uses ComplianceGateway."""
    import inspect
    import holler.main as main_module
    source = inspect.getsource(main_module)
    assert "ComplianceGateway" in source, "main.py must instantiate ComplianceGateway"
    assert "originate_checked" in source, "main.py must use gateway.originate_checked()"


def test_main_uses_number_pool():
    """main.py imports and uses NumberPool."""
    import inspect
    import holler.main as main_module
    source = inspect.getsource(main_module)
    assert "NumberPool" in source
    assert "pool.checkout" in source
    assert "pool.release" in source


def test_main_uses_recording():
    """main.py imports and uses recording functions."""
    import inspect
    import holler.main as main_module
    source = inspect.getsource(main_module)
    assert "start_recording" in source
    assert "stop_recording" in source


def test_main_has_dtmf_handler():
    """main.py registers a DTMF opt-out handler."""
    import inspect
    import holler.main as main_module
    source = inspect.getsource(main_module)
    assert "DTMF" in source
    assert "consent_db.record_optout" in source


def test_main_has_us_compliance_module():
    """main.py instantiates USComplianceModule and JurisdictionRouter."""
    import inspect
    import holler.main as main_module
    source = inspect.getsource(main_module)
    assert "USComplianceModule" in source
    assert "JurisdictionRouter" in source


def test_main_no_direct_esl_originate_in_originate_call():
    """_originate_call uses gateway.originate_checked(), not direct esl.originate()."""
    import inspect
    import holler.main as main_module

    # Get source of _originate_call specifically
    source = inspect.getsource(main_module._originate_call)
    assert "originate_checked" in source, "_originate_call must use gateway.originate_checked()"
    # Direct esl.originate() should NOT appear in _originate_call
    assert "esl.originate(" not in source, "_originate_call must not call esl.originate() directly"
