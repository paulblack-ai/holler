"""TCPA compliance checks for US outbound calls.

Implements time-of-day and consent verification checks per D-11 and COMP-02.

TCPA (Telephone Consumer Protection Act) requires:
- Calls only between 8am and 9pm in the RECIPIENT'S local timezone.
- Prior express consent before calling.

Per D-13: If the destination timezone cannot be determined, the call is denied
(fail-closed — unknown NPA = deny).
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import TYPE_CHECKING, Optional
from zoneinfo import ZoneInfo

from holler.core.compliance.gateway import ComplianceResult
from holler.countries.us.timezones import get_timezone_for_npa

if TYPE_CHECKING:
    from holler.core.compliance.consent_db import ConsentDB


# TCPA allowed calling window (recipient local time)
TCPA_HOUR_START = 8   # 8:00 AM
TCPA_HOUR_END = 21    # 9:00 PM (calls must complete before 9 PM)


def check_time_of_day(
    destination: str,
    now: Optional[datetime] = None,
) -> ComplianceResult:
    """Check whether the current time is within TCPA-allowed calling hours.

    Allowed window: 8:00 AM to 9:00 PM in the RECIPIENT'S local timezone,
    derived from the destination's area code (NPA). Per D-11, D-13.

    Unknown area codes FAIL CLOSED per D-13: if we cannot determine the
    recipient's timezone, we deny the call.

    Args:
        destination: E.164 destination phone number (e.g. "+12125551234").
        now: Current UTC datetime for testing. Defaults to datetime.now(UTC).

    Returns:
        ComplianceResult with check_type="tcpa_tod".
        - passed=False, reason="unknown_npa:{npa}" if NPA not in map.
        - passed=False, reason="outside_tcpa_hours:{HH:MM TZ}" if outside window.
        - passed=True, reason="within_tcpa_hours:{HH:MM TZ}" if within window.
    """
    if now is None:
        now = datetime.now(timezone.utc)

    # Extract NPA for error messages
    npa = "unknown"
    if destination and destination.startswith("+1") and len(destination) >= 5:
        npa = destination[2:5]

    tz_name = get_timezone_for_npa(destination)
    if tz_name is None:
        return ComplianceResult(
            passed=False,
            reason=f"unknown_npa:{npa}",
            check_type="tcpa_tod",
            audit_fields={
                "destination": destination,
                "npa": npa,
                "check": "tcpa_time_of_day",
                "denial_reason": "npa_not_in_timezone_map",
            },
        )

    tz = ZoneInfo(tz_name)
    local_now = now.astimezone(tz)
    local_hour = local_now.hour
    local_time_str = local_now.strftime("%H:%M")
    tz_abbr = local_now.strftime("%Z")

    within_window = TCPA_HOUR_START <= local_hour < TCPA_HOUR_END

    if not within_window:
        return ComplianceResult(
            passed=False,
            reason=f"outside_tcpa_hours:{local_time_str} {tz_abbr}",
            check_type="tcpa_tod",
            audit_fields={
                "destination": destination,
                "npa": npa,
                "local_time": local_time_str,
                "timezone": tz_name,
                "tz_abbr": tz_abbr,
                "hour_start": TCPA_HOUR_START,
                "hour_end": TCPA_HOUR_END,
                "check": "tcpa_time_of_day",
            },
        )

    return ComplianceResult(
        passed=True,
        reason=f"within_tcpa_hours:{local_time_str} {tz_abbr}",
        check_type="tcpa_tod",
        audit_fields={
            "destination": destination,
            "npa": npa,
            "local_time": local_time_str,
            "timezone": tz_name,
            "tz_abbr": tz_abbr,
            "check": "tcpa_time_of_day",
        },
    )


async def check_consent(
    destination: str,
    consent_db: "ConsentDB",
) -> ComplianceResult:
    """Check whether prior express consent exists for the destination number.

    Queries the ConsentDB for the most recent consent record. Returns a denial
    if no consent record exists or if the latest record is a revocation (opt-out).

    Per D-11, D-14: Consent is append-only; revocations are new rows, not updates.
    This check reads the current state — if the latest row is an opt-out, consent
    is not present.

    Args:
        destination: E.164 destination phone number (e.g. "+12125551234").
        consent_db: Initialized ConsentDB instance.

    Returns:
        ComplianceResult with check_type="tcpa_consent".
        - passed=False, reason="no_prior_consent" if consent not found.
        - passed=True, reason="consent_verified" if consent present.
    """
    has_consent = await consent_db.has_consent(destination)

    if not has_consent:
        return ComplianceResult(
            passed=False,
            reason="no_prior_consent",
            check_type="tcpa_consent",
            audit_fields={
                "destination": destination,
                "check": "tcpa_consent",
                "consent_found": False,
            },
        )

    return ComplianceResult(
        passed=True,
        reason="consent_verified",
        check_type="tcpa_consent",
        audit_fields={
            "destination": destination,
            "check": "tcpa_consent",
            "consent_found": True,
        },
    )
