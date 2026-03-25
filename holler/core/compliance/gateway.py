"""Compliance gateway — mandatory pre-originate gate and type contracts.

Defines the ComplianceModule ABC, ComplianceResult dataclass, and
ComplianceGateway orchestrator that all outbound calls must pass through.
Per D-07, D-08, COMP-01 (CONTEXT.md).

The structural guarantee: esl.originate() can only be called from within
ComplianceGateway.originate_checked(). There is no other call path.
"""
from __future__ import annotations

import asyncio
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, Optional

if TYPE_CHECKING:
    from holler.core.telecom.session import TelecomSession
    from holler.core.compliance.audit import AuditLog
    from holler.core.freeswitch.esl import FreeSwitchESL
    from holler.core.telecom.pool import NumberPool
    from holler.core.sms.client import SMSClient


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


class ComplianceGateway:
    """Mandatory gate. Wraps ESL originate. No call exits without clearing this.

    The ComplianceGateway is the single path to esl.originate() for all outbound
    calls. It is structurally impossible to call esl.originate() without running
    a compliance check first (D-07, COMP-01).

    Fail-closed on any error — exception in check, timeout, or unknown module
    all result in a denied call. The DID is returned to the pool on any block.
    An audit log entry is written on every check, pass or fail (D-20, COMP-05).
    """

    def __init__(
        self,
        router: "Any",  # JurisdictionRouter — avoid circular import
        audit_log: "AuditLog",
        timeout: float = 2.0,
    ) -> None:
        """Initialize the ComplianceGateway.

        Args:
            router: JurisdictionRouter that maps E.164 prefixes to ComplianceModule.
            audit_log: AuditLog to write every compliance check result to.
            timeout: Maximum seconds to wait for check_outbound() to complete.
                     Exceeding this limit blocks the call (fail-closed). Default: 2.0s.
        """
        self._router = router
        self._audit = audit_log
        self._timeout = timeout

    async def originate_checked(
        self,
        esl: "FreeSwitchESL",
        pool: "NumberPool",
        session: "TelecomSession",
    ) -> str:
        """Run compliance check, then originate. Returns call_uuid.

        This is the ONLY path to esl.originate() for outbound calls.
        Fail-closed on any error — exception in check, timeout, or unknown module.

        Args:
            esl: FreeSwitchESL client to originate the call through.
            pool: NumberPool to release the DID back to on compliance block.
            session: TelecomSession for this call attempt.

        Returns:
            FreeSWITCH call UUID from esl.originate().

        Raises:
            ComplianceBlockError: If the compliance check denies the call, times out,
                                  raises an exception, or no module exists for the destination.
        """
        # --- Run compliance check (fail-closed on any error) ---
        try:
            module = self._router.resolve(session.destination)
            result = await asyncio.wait_for(
                module.check_outbound(session.destination, session),
                timeout=self._timeout,
            )
        except NoComplianceModuleError:
            result = ComplianceResult(
                passed=False,
                reason="no_compliance_module",
                check_type="jurisdiction",
                audit_fields={"destination_prefix": session.destination[:4]},
            )
        except asyncio.TimeoutError:
            result = ComplianceResult(
                passed=False,
                reason="compliance_check_timeout",
                check_type="timeout",
                audit_fields={"timeout_s": self._timeout},
            )
        except Exception as e:
            result = ComplianceResult(
                passed=False,
                reason=f"compliance_check_error: {str(e)}",
                check_type="error",
                audit_fields={"error": str(e)},
            )

        # --- Always write audit log — pass or fail (D-20, COMP-05) ---
        await self._audit.write({
            "call_uuid": session.call_uuid,
            "session_uuid": session.session_uuid,
            "check_type": result.check_type,
            "destination": session.destination,
            "result": "allow" if result.passed else "deny",
            "reason": result.reason,
            "did": session.did,
            **result.audit_fields,
        })

        session.compliance_result = result

        if not result.passed:
            await pool.release(session.did)  # Return DID to pool on block
            raise ComplianceBlockError(result.reason)

        # --- Compliance passed — originate the call ---
        call_uuid = await esl.originate(session.destination, session.session_uuid)
        session.call_uuid = call_uuid
        return call_uuid

    async def sms_checked(
        self,
        sms_client: "SMSClient",
        pool: "NumberPool",
        session: "TelecomSession",
        message: str,
        log_id: str,
    ) -> str:
        """Run compliance check, then send SMS. Returns log_id.

        This is the ONLY path to sms_client.send() for outbound SMS.
        Provides the same structural compliance guarantee as originate_checked()
        for voice calls (D-07): it is structurally impossible to send an SMS
        without clearing this compliance gate.

        Fail-closed on any error — exception in check, timeout, or unknown module
        all result in a denied send. The DID is returned to the pool on any block.
        An audit log entry is written on every check, pass or fail.

        Args:
            sms_client: SMSClient instance to send through after compliance passes.
            pool: NumberPool to release the DID back to on compliance block.
            session: TelecomSession for this SMS attempt.
            message: UTF-8 message text to send.
            log_id: Unique message identifier (passed to sms_client.send() and
                    used for delivery status tracking).

        Returns:
            log_id on success (same value passed in).

        Raises:
            ComplianceBlockError: If the compliance check denies the SMS, times out,
                                  raises an exception, or no module exists for the
                                  destination. The DID is released before raising.
        """
        # --- Run compliance check (fail-closed on any error) ---
        try:
            module = self._router.resolve(session.destination)
            result = await asyncio.wait_for(
                module.check_outbound(session.destination, session),
                timeout=self._timeout,
            )
        except NoComplianceModuleError:
            result = ComplianceResult(
                passed=False,
                reason="no_compliance_module",
                check_type="jurisdiction",
                audit_fields={"destination_prefix": session.destination[:4]},
            )
        except asyncio.TimeoutError:
            result = ComplianceResult(
                passed=False,
                reason="compliance_check_timeout",
                check_type="timeout",
                audit_fields={"timeout_s": self._timeout},
            )
        except Exception as e:
            result = ComplianceResult(
                passed=False,
                reason=f"compliance_check_error: {str(e)}",
                check_type="error",
                audit_fields={"error": str(e)},
            )

        # --- Always write audit log — pass or fail (D-20, COMP-05) ---
        await self._audit.write({
            "channel": "sms",
            "message_log_id": log_id,
            "session_uuid": session.session_uuid,
            "check_type": result.check_type,
            "destination": session.destination,
            "result": "allow" if result.passed else "deny",
            "reason": result.reason,
            "did": session.did,
            **result.audit_fields,
        })

        session.compliance_result = result

        if not result.passed:
            await pool.release(session.did)  # Return DID to pool on block
            raise ComplianceBlockError(result.reason)

        # --- Compliance passed — send the SMS ---
        await sms_client.send(session.destination, message, log_id)
        return log_id
