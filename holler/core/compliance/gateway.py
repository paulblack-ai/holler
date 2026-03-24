"""Compliance gateway type contracts.

Defines the ComplianceModule ABC and ComplianceResult dataclass that all
country modules must implement. Per D-08 (CONTEXT.md).

NOTE: The ComplianceGateway class (which orchestrates the gateway logic and
wraps esl.originate) will be added in Plan 03. This file defines only the ABC
and data types.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict

if TYPE_CHECKING:
    from holler.core.telecom.session import TelecomSession


@dataclass
class ComplianceResult:
    """Result of a compliance check.

    Every compliance check must produce a ComplianceResult. The result carries
    the pass/fail decision, a human-readable reason, the check type identifier,
    and any audit fields needed for the audit log entry.

    Per D-08: check_outbound() -> ComplianceResult (allow/deny with reason and
    audit fields).
    """

    passed: bool
    reason: str
    check_type: str
    audit_fields: Dict[str, Any] = field(default_factory=dict)


class ComplianceModule(ABC):
    """Abstract base class for jurisdiction compliance modules.

    Every country module must subclass ComplianceModule and implement
    check_outbound(). The jurisdiction router calls the correct module based
    on the E.164 destination prefix (D-08, D-09).

    Adding a new country = implementing this interface. Per COMP-06.
    """

    @abstractmethod
    async def check_outbound(
        self,
        destination: str,
        session: "TelecomSession",
    ) -> ComplianceResult:
        """Check whether an outbound call to `destination` is permitted.

        This is the single contract all country modules must fulfill. It runs
        BEFORE FreeSWITCH originate is issued (D-07) — there is no call path
        that bypasses this check.

        Args:
            destination: E.164 destination phone number (e.g. "+15550001234").
            session: TelecomSession carrying DID, jurisdiction, consent state,
                     and any prior compliance results for this call attempt.

        Returns:
            ComplianceResult with passed=True (call may proceed) or
            passed=False (call must be blocked).

        Raises:
            ComplianceBlockError: May be raised instead of returning a failed
                result when a hard block condition is detected (e.g. DNC match
                with certainty). Callers should treat this equivalently to a
                failed ComplianceResult.
        """


class ComplianceBlockError(Exception):
    """Raised when a compliance check definitively blocks an outbound call.

    Callers must not proceed with the call when this exception is raised.
    Per D-07: structurally impossible to place an unchecked outbound call.
    """


class NoComplianceModuleError(Exception):
    """Raised when no compliance module exists for the destination jurisdiction.

    The system fails closed — unknown jurisdictions are denied, not allowed.
    Per D-09: if no module exists for a destination, the call is denied by default.
    """
