"""US jurisdiction compliance module — TCPA + DNC enforcement.

Implements the ComplianceModule ABC for +1 (United States) destinations.
Enforces all federal TCPA requirements per D-11, D-12, COMP-02, COMP-03:

1. DNC list check (cheapest — single SQLite PRIMARY KEY lookup)
2. Time-of-day check (no I/O — pure timezone math with zoneinfo)
3. Consent verification (SQLite query)

Check order rationale: DNC is O(1) index scan, cheapest to run and catches the
most definitive denials first. Time-of-day is pure computation with no I/O.
Consent requires a database query with a WHERE clause. Short-circuit on first
failure minimizes work per call attempt.

Per D-13: Fail-closed design — unknown area codes are denied, not allowed.

Usage:
    module = USComplianceModule(consent_db=consent_db, dnc_list=dnc_list)
    result = await module.check_outbound("+12125551234", session)
"""
from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from holler.core.compliance.gateway import ComplianceModule, ComplianceResult
from holler.countries.us.dnc_check import check_dnc
from holler.countries.us.tcpa import check_consent, check_time_of_day

if TYPE_CHECKING:
    from holler.core.compliance.consent_db import ConsentDB
    from holler.core.compliance.dnc import DNCList
    from holler.core.telecom.session import TelecomSession


class USComplianceModule(ComplianceModule):
    """US jurisdiction compliance: TCPA + DNC enforcement.

    Enforces federal TCPA requirements for all calls to +1 (US) destinations.
    Must be registered with the JurisdictionRouter for the "+1" prefix.

    Per D-11 (time-of-day + consent), D-12 (DNC check), D-13 (fail-closed NPA).
    Implements COMP-02 (TCPA) and COMP-03 (DNC list check) requirements.

    Check order (fastest to slowest, fail-closes on first denial):
    1. DNC list   — single SQLite PRIMARY KEY lookup
    2. Time-of-day — pure Python timezone math, no I/O
    3. Consent     — SQLite query with WHERE + ORDER BY

    All checks return ComplianceResult. The module short-circuits on first
    failure — if DNC matches, time-of-day and consent are never evaluated.
    This minimizes per-call latency and database load.
    """

    def __init__(self, consent_db: "ConsentDB", dnc_list: "DNCList") -> None:
        """Initialize the US compliance module with data layer dependencies.

        Args:
            consent_db: Initialized ConsentDB for prior consent lookups.
            dnc_list: Initialized DNCList for DNC status lookups.
        """
        self._consent_db = consent_db
        self._dnc_list = dnc_list

    async def check_outbound(
        self,
        destination: str,
        session: "TelecomSession",
        now: Optional[datetime] = None,
    ) -> ComplianceResult:
        """Run all US compliance checks in order. First failure short-circuits.

        Check order:
        1. DNC list (cheapest — single SQLite PRIMARY KEY lookup)
        2. Time-of-day (no I/O — pure timezone math with zoneinfo)
        3. Consent verification (SQLite query)

        Args:
            destination: E.164 destination phone number (e.g. "+12125551234").
            session: TelecomSession carrying DID, jurisdiction, and call context.
            now: Optional UTC datetime for deterministic testing. Defaults to
                 current UTC time if not provided.

        Returns:
            ComplianceResult. If passed=False, the call must be blocked.
            If passed=True (check_type="us_all_passed"), the call may proceed.
        """
        # --- Check 1: DNC list ---
        # Cheapest check — single PRIMARY KEY lookup. Run first to short-circuit
        # most definitive denials with minimal work.
        dnc_result = await check_dnc(destination, self._dnc_list)
        if not dnc_result.passed:
            return dnc_result

        # --- Check 2: Time-of-day (TCPA) ---
        # Pure timezone math — no I/O. Fails closed for unknown NPAs (D-13).
        tod_result = check_time_of_day(destination, now=now)
        if not tod_result.passed:
            return tod_result

        # --- Check 3: Consent verification (TCPA) ---
        # Requires a DB query. Run last since it's the costliest.
        consent_result = await check_consent(destination, self._consent_db)
        if not consent_result.passed:
            return consent_result

        # All checks passed — call may proceed.
        return ComplianceResult(
            passed=True,
            reason="all_checks_passed",
            check_type="us_all_passed",
            audit_fields={
                "destination": destination,
                "session_uuid": getattr(session, "session_uuid", None),
                "call_uuid": getattr(session, "call_uuid", None),
                "checks_run": ["dnc", "tcpa_tod", "tcpa_consent"],
                "jurisdiction": "us",
            },
        )
