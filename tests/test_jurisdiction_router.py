"""Tests for JurisdictionRouter — E.164 prefix mapping to compliance modules.

Tests cover:
- resolve("+1...") returns US module when "+1" registered
- resolve("+44...") returns UK module when "+44" registered
- resolve("+86...") raises NoComplianceModuleError when "+86" not registered (fail-closed)
- register/resolve round-trip
- Longer prefix takes priority over shorter prefix (longest-match-first)
- list_jurisdictions() returns dict of prefix -> module class name
"""
from __future__ import annotations

import pytest

from holler.core.compliance.gateway import (
    ComplianceModule,
    ComplianceResult,
    NoComplianceModuleError,
)
from holler.core.telecom.router import JurisdictionRouter


# ---------------------------------------------------------------------------
# Stub compliance modules
# ---------------------------------------------------------------------------

class StubUSModule(ComplianceModule):
    async def check_outbound(self, destination, session):
        return ComplianceResult(passed=True, reason="us_allowed", check_type="tcpa")


class StubUKModule(ComplianceModule):
    async def check_outbound(self, destination, session):
        return ComplianceResult(passed=True, reason="uk_allowed", check_type="ofcom")


class StubSFModule(ComplianceModule):
    """Stub for San Francisco area code (+1415) — longer prefix than US (+1)."""
    async def check_outbound(self, destination, session):
        return ComplianceResult(passed=True, reason="sf_allowed", check_type="tcpa_sf")


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

def test_resolve_us_prefix():
    """resolve('+14155551234') returns US module when '+1' is registered."""
    router = JurisdictionRouter()
    us_module = StubUSModule()
    router.register("+1", us_module)

    result = router.resolve("+14155551234")

    assert result is us_module


def test_resolve_uk_prefix():
    """resolve('+447911123456') returns UK module when '+44' is registered."""
    router = JurisdictionRouter()
    uk_module = StubUKModule()
    router.register("+44", uk_module)

    result = router.resolve("+447911123456")

    assert result is uk_module


def test_resolve_unregistered_prefix_raises_no_module_error():
    """resolve('+8613800138000') raises NoComplianceModuleError when '+86' not registered."""
    router = JurisdictionRouter()
    router.register("+1", StubUSModule())  # US is registered, China is not

    with pytest.raises(NoComplianceModuleError):
        router.resolve("+8613800138000")


def test_resolve_empty_router_raises_no_module_error():
    """resolve() on a router with no registered modules raises NoComplianceModuleError."""
    router = JurisdictionRouter()

    with pytest.raises(NoComplianceModuleError):
        router.resolve("+14155551234")


def test_register_then_resolve_returns_registered_module():
    """register('+1', module) then resolve('+14155551234') returns the same module instance."""
    router = JurisdictionRouter()
    us_module = StubUSModule()
    router.register("+1", us_module)

    resolved = router.resolve("+14155551234")

    assert resolved is us_module


def test_longer_prefix_takes_priority_over_shorter():
    """'+1415' registered takes priority over '+1' for San Francisco numbers."""
    router = JurisdictionRouter()
    us_module = StubUSModule()
    sf_module = StubSFModule()

    router.register("+1", us_module)
    router.register("+1415", sf_module)

    # San Francisco number — should match longer prefix "+1415"
    resolved_sf = router.resolve("+14155559999")
    assert resolved_sf is sf_module, "Longer prefix '+1415' should win over '+1'"

    # Non-SF US number — should match shorter prefix "+1"
    resolved_us = router.resolve("+12125551234")
    assert resolved_us is us_module, "'+1' should match non-SF US number"


def test_multiple_prefixes_registered():
    """Both +1 and +44 registered — each resolves to the correct module."""
    router = JurisdictionRouter()
    us_module = StubUSModule()
    uk_module = StubUKModule()

    router.register("+1", us_module)
    router.register("+44", uk_module)

    assert router.resolve("+14155551234") is us_module
    assert router.resolve("+447911123456") is uk_module


def test_list_jurisdictions_returns_prefix_to_class_name():
    """list_jurisdictions() returns a dict mapping prefix to module class name."""
    router = JurisdictionRouter()
    router.register("+1", StubUSModule())
    router.register("+44", StubUKModule())

    result = router.list_jurisdictions()

    assert isinstance(result, dict)
    assert result["+1"] == "StubUSModule"
    assert result["+44"] == "StubUKModule"


def test_list_jurisdictions_empty_router():
    """list_jurisdictions() on empty router returns empty dict."""
    router = JurisdictionRouter()
    assert router.list_jurisdictions() == {}


def test_resolve_error_message_obscures_full_destination():
    """NoComplianceModuleError message should not expose the full phone number."""
    router = JurisdictionRouter()

    with pytest.raises(NoComplianceModuleError) as exc_info:
        router.resolve("+8613800138000")

    # The error message should truncate the destination (not expose full number)
    # The plan specifies destination[:4] in the error message
    error_msg = str(exc_info.value)
    assert "+861" in error_msg or "+86" in error_msg  # prefix exposed is fine
    assert "13800138000" not in error_msg  # full number should not appear
