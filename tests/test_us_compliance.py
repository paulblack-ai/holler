"""Tests for the US compliance module (USComplianceModule).

Tests cover all TCPA compliance checks per COMP-02, COMP-03, D-11, D-12, D-13:
- DNC list denial (dnc_listed)
- Time-of-day denial (outside_tcpa_hours)
- Unknown NPA denial (unknown_npa)
- Consent denial (no_prior_consent)
- All-pass path (all checks pass)
- DNC short-circuit (DNC match skips further checks)
- ComplianceResult audit_fields presence

Test design:
- Uses real ConsentDB and DNCList with in-memory SQLite (tmp_path)
- Patches check_time_of_day via the 'now' parameter (no monkey-patching needed)
- asyncio.get_event_loop().run_until_complete() for compatibility
"""
import asyncio
from datetime import datetime, timezone

import pytest

from holler.core.compliance.consent_db import ConsentDB
from holler.core.compliance.dnc import DNCList
from holler.countries.us.module import USComplianceModule


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

loop = asyncio.get_event_loop()


@pytest.fixture
def consent_db(tmp_path):
    """Real ConsentDB backed by temporary SQLite file."""
    db = ConsentDB(db_path=str(tmp_path / "consent.db"))
    loop.run_until_complete(db.initialize())
    yield db
    loop.run_until_complete(db.close())


@pytest.fixture
def dnc_list(tmp_path):
    """Real DNCList backed by temporary SQLite file."""
    dnc = DNCList(db_path=str(tmp_path / "dnc.db"))
    loop.run_until_complete(dnc.initialize())
    yield dnc
    loop.run_until_complete(dnc.close())


@pytest.fixture
def us_module(consent_db, dnc_list):
    """USComplianceModule with real in-memory-backed data stores."""
    return USComplianceModule(consent_db=consent_db, dnc_list=dnc_list)


def make_session(destination: str = "+12125551234"):
    """Create a minimal TelecomSession-like mock for testing.

    We use a simple namespace so tests don't need the full session machinery.
    """
    from types import SimpleNamespace
    return SimpleNamespace(
        session_uuid="test-session-uuid",
        call_uuid="test-call-uuid",
        did="+18005550001",
        destination=destination,
        jurisdiction="us",
    )


# A fixed "business hours" datetime — 2pm Eastern on a Tuesday
BUSINESS_HOURS_UTC = datetime(2024, 1, 16, 19, 0, 0, tzinfo=timezone.utc)  # 2pm EST = 19:00 UTC

# A fixed "outside hours" datetime — 11pm Eastern
OUTSIDE_HOURS_UTC = datetime(2024, 1, 16, 4, 0, 0, tzinfo=timezone.utc)    # 11pm EST = 04:00 UTC next day


# ---------------------------------------------------------------------------
# Tests: Individual failure paths
# ---------------------------------------------------------------------------

def test_dnc_listed_returns_denial(us_module, dnc_list, consent_db):
    """check_outbound() returns passed=False with reason 'dnc_listed' for DNC numbers."""
    destination = "+12125550001"
    session = make_session(destination)

    # Add number to DNC list
    loop.run_until_complete(dnc_list.add_number(destination))
    # Also grant consent so we know the denial is from DNC, not consent
    loop.run_until_complete(consent_db.record_consent(destination, "express", source="api"))

    result = loop.run_until_complete(
        us_module.check_outbound(destination, session, now=BUSINESS_HOURS_UTC)
    )

    assert result.passed is False
    assert result.reason == "dnc_listed"
    assert result.check_type == "dnc"


def test_outside_tcpa_hours_returns_denial(us_module, consent_db):
    """check_outbound() returns passed=False containing 'outside_tcpa_hours' outside 8am-9pm."""
    destination = "+12125550002"
    session = make_session(destination)

    # Grant consent so the denial is from time-of-day, not consent
    loop.run_until_complete(consent_db.record_consent(destination, "express", source="api"))

    # 11pm Eastern = outside TCPA hours
    result = loop.run_until_complete(
        us_module.check_outbound(destination, session, now=OUTSIDE_HOURS_UTC)
    )

    assert result.passed is False
    assert "outside_tcpa_hours" in result.reason
    assert result.check_type == "tcpa_tod"


def test_no_prior_consent_returns_denial(us_module):
    """check_outbound() returns passed=False with reason 'no_prior_consent' when no consent."""
    destination = "+12125550003"
    session = make_session(destination)

    # No consent recorded — should deny

    result = loop.run_until_complete(
        us_module.check_outbound(destination, session, now=BUSINESS_HOURS_UTC)
    )

    assert result.passed is False
    assert result.reason == "no_prior_consent"
    assert result.check_type == "tcpa_consent"


def test_unknown_npa_returns_denial(us_module, consent_db):
    """check_outbound() returns passed=False with reason containing 'unknown_npa' for unmapped area codes."""
    destination = "+19995550001"  # 999 is not a valid US NPA
    session = make_session(destination)

    # Grant consent — denial should come from unknown NPA
    loop.run_until_complete(consent_db.record_consent(destination, "express", source="api"))

    result = loop.run_until_complete(
        us_module.check_outbound(destination, session, now=BUSINESS_HOURS_UTC)
    )

    assert result.passed is False
    assert "unknown_npa" in result.reason
    assert result.check_type == "tcpa_tod"


def test_all_checks_pass_returns_success(us_module, consent_db):
    """check_outbound() returns passed=True when not on DNC, within hours, and has consent."""
    destination = "+12125550004"
    session = make_session(destination)

    # Grant consent
    loop.run_until_complete(consent_db.record_consent(destination, "express", source="api"))

    result = loop.run_until_complete(
        us_module.check_outbound(destination, session, now=BUSINESS_HOURS_UTC)
    )

    assert result.passed is True
    assert result.check_type == "us_all_passed"


# ---------------------------------------------------------------------------
# Tests: Short-circuit and audit_fields
# ---------------------------------------------------------------------------

def test_dnc_short_circuits_skips_other_checks(us_module, dnc_list):
    """DNC check runs first — if DNC match, consent and time-of-day are skipped."""
    destination = "+12125550005"
    session = make_session(destination)

    # Add to DNC but do NOT grant consent, and use outside-hours time
    # If short-circuit works correctly, we get dnc_listed (not no_prior_consent)
    loop.run_until_complete(dnc_list.add_number(destination))

    result = loop.run_until_complete(
        us_module.check_outbound(destination, session, now=OUTSIDE_HOURS_UTC)
    )

    assert result.passed is False
    assert result.reason == "dnc_listed"
    assert result.check_type == "dnc"


def test_result_has_audit_fields(us_module, consent_db):
    """check_outbound() returns a ComplianceResult with audit_fields containing check details."""
    destination = "+12125550006"
    session = make_session(destination)

    # Grant consent for all-pass path
    loop.run_until_complete(consent_db.record_consent(destination, "express", source="api"))

    result = loop.run_until_complete(
        us_module.check_outbound(destination, session, now=BUSINESS_HOURS_UTC)
    )

    assert isinstance(result.audit_fields, dict)
    assert len(result.audit_fields) > 0


def test_failed_result_has_audit_fields_with_destination(us_module, dnc_list):
    """Failing check returns audit_fields with destination number."""
    destination = "+12125550007"
    session = make_session(destination)

    loop.run_until_complete(dnc_list.add_number(destination))

    result = loop.run_until_complete(
        us_module.check_outbound(destination, session, now=BUSINESS_HOURS_UTC)
    )

    assert result.passed is False
    assert "destination" in result.audit_fields
    assert result.audit_fields["destination"] == destination


# ---------------------------------------------------------------------------
# Tests: USComplianceModule is a proper ComplianceModule subclass
# ---------------------------------------------------------------------------

def test_us_module_is_compliance_module_subclass(us_module):
    """USComplianceModule must implement the ComplianceModule ABC."""
    from holler.core.compliance.gateway import ComplianceModule
    assert isinstance(us_module, ComplianceModule)
    assert issubclass(USComplianceModule, ComplianceModule)
