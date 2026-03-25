"""ToolExecutor — dispatches LLM tool calls to Holler actions.

The ToolExecutor is the bridge between the LLM tool-use protocol and the
actual Holler subsystems (FreeSWITCH ESL, SMS, compliance gateway).

Compliance blocks produce {"status": "blocked", "reason": ...} not exceptions
(D-02). All errors are caught and returned as structured JSON — the caller
never receives an unhandled exception from execute().

Per D-03: transfer tool runs compliance check on destination before ESL command.

Exports:
    ToolExecutor: Dispatches tool calls to Holler actions.
"""
from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, Any, Dict

import structlog

if TYPE_CHECKING:
    from holler.core.freeswitch.esl import FreeSwitchESL
    from holler.core.telecom.pool import NumberPool
    from holler.core.compliance.gateway import ComplianceGateway
    from holler.core.telecom.session import TelecomSession

from holler.core.compliance.gateway import ComplianceBlockError

logger = structlog.get_logger()


class ToolExecutor:
    """Dispatches LLM tool invocations to the appropriate Holler actions.

    Wraps ESL, SMS, and compliance gateway with a uniform async execute()
    interface. Returns structured JSON for all outcomes including errors and
    compliance blocks.

    Usage:
        executor = ToolExecutor(esl=esl, sms_client=sms, compliance_gateway=gw, pool=pool)
        result = await executor.execute("hangup", {"call_uuid": "abc"}, session)
        # result: {"status": "ok"}
    """

    def __init__(
        self,
        esl: "FreeSwitchESL",
        sms_client: Any,
        compliance_gateway: "ComplianceGateway",
        pool: "NumberPool",
    ) -> None:
        """Initialize ToolExecutor with Holler subsystem references.

        Args:
            esl: FreeSwitchESL client for call control commands.
            sms_client: SMS client (SMPP or modem) for sending messages.
            compliance_gateway: ComplianceGateway for pre-action compliance checks.
            pool: NumberPool for DID checkout/release during SMS sessions.
        """
        self._esl = esl
        self._sms = sms_client
        self._gateway = compliance_gateway
        self._pool = pool

    async def execute(
        self,
        tool_name: str,
        arguments: Dict[str, Any],
        session: "TelecomSession",
    ) -> Dict[str, Any]:
        """Execute a tool call by name and return a structured JSON result.

        Compliance blocks return {"status": "blocked", "reason": ...} (D-02).
        All other exceptions return {"status": "error", "reason": ...}.
        The caller never receives an unhandled exception from this method.

        Args:
            tool_name: One of "call", "sms", "hangup", "transfer".
            arguments: Parsed tool arguments dict from the LLM.
            session: Active TelecomSession for this conversation.

        Returns:
            Dict with at minimum a "status" key. "ok" on success.
        """
        try:
            if tool_name == "call":
                return await self._execute_call(arguments, session)
            elif tool_name == "sms":
                return await self._execute_sms(arguments, session)
            elif tool_name == "hangup":
                return await self._execute_hangup(arguments, session)
            elif tool_name == "transfer":
                return await self._execute_transfer(arguments, session)
            else:
                return {"status": "error", "reason": f"unknown_tool: {tool_name}"}
        except ComplianceBlockError as e:
            logger.warning("tool.compliance_block", tool=tool_name, reason=str(e))
            return {"status": "blocked", "reason": str(e)}
        except Exception as e:
            logger.error("tool.error", tool=tool_name, error=str(e))
            return {"status": "error", "reason": str(e)}

    async def _execute_call(
        self,
        args: Dict[str, Any],
        session: "TelecomSession",
    ) -> Dict[str, Any]:
        """Place an outbound phone call via the compliance gateway.

        Args:
            args: Must contain "destination" (E.164). "prompt" is optional (nullable).
            session: Active TelecomSession.

        Returns:
            {"status": "ok", "call_uuid": str}
        """
        call_uuid = await self._gateway.originate_checked(self._esl, self._pool, session)
        logger.info("tool.call.ok", call_uuid=call_uuid, destination=args.get("destination"))
        return {"status": "ok", "call_uuid": call_uuid}

    async def _execute_sms(
        self,
        args: Dict[str, Any],
        session: "TelecomSession",
    ) -> Dict[str, Any]:
        """Send an SMS message via the compliance gateway.

        Constructs a new TelecomSession for the SMS interaction with all
        required fields populated (session_uuid, call_uuid, did, destination,
        jurisdiction). SMS sessions have call_uuid="" since there is no
        associated voice call.

        Args:
            args: Must contain "destination" (E.164) and "message" (str).
            session: Parent TelecomSession providing jurisdiction and DID context.

        Returns:
            {"status": "ok", "message_id": str}
        """
        # Import here to avoid circular imports at module load time
        from holler.core.telecom.session import TelecomSession

        destination = args["destination"]
        message = args["message"]
        log_id = str(uuid.uuid4())

        # Build a complete TelecomSession for the SMS — all non-Optional fields
        # must be explicitly set (omitting any causes TypeError).
        session_for_sms = TelecomSession(
            session_uuid=str(uuid.uuid4()),
            call_uuid="",           # No voice call for SMS
            did=session.did,
            destination=destination,
            jurisdiction=session.jurisdiction,
        )

        await self._gateway.sms_checked(self._sms, self._pool, session_for_sms, message, log_id)
        logger.info("tool.sms.ok", destination=destination, message_id=log_id)
        return {"status": "ok", "message_id": log_id}

    async def _execute_hangup(
        self,
        args: Dict[str, Any],
        session: "TelecomSession",
    ) -> Dict[str, Any]:
        """Terminate an active call by UUID.

        Args:
            args: Must contain "call_uuid" (str).
            session: Active TelecomSession (unused but kept for API uniformity).

        Returns:
            {"status": "ok"}
        """
        call_uuid = args["call_uuid"]
        await self._esl.hangup(call_uuid)
        logger.info("tool.hangup.ok", call_uuid=call_uuid)
        return {"status": "ok"}

    async def _execute_transfer(
        self,
        args: Dict[str, Any],
        session: "TelecomSession",
    ) -> Dict[str, Any]:
        """Blind transfer an active call to a new destination (D-03).

        Runs compliance check on the transfer destination before issuing the
        ESL transfer command. Raises ComplianceBlockError if check fails
        (caught by execute() and returned as {"status": "blocked"}).

        Args:
            args: Must contain "call_uuid" (str) and "destination" (E.164).
            session: Active TelecomSession providing jurisdiction context.

        Returns:
            {"status": "ok", "transferred_to": str}
        """
        call_uuid = args["call_uuid"]
        destination = args["destination"]

        # Compliance check on transfer destination (D-03)
        module = self._gateway._router.resolve(destination)
        result = await module.check_outbound(destination, session)
        if not result.passed:
            raise ComplianceBlockError(
                getattr(result, "reason", f"transfer blocked for {destination}")
            )

        # ESL blind transfer command
        cmd = f"api uuid_transfer {call_uuid} sofia/gateway/sip_trunk/{destination}"
        await self._esl.send_raw(cmd)
        logger.info("tool.transfer.ok", call_uuid=call_uuid, destination=destination)
        return {"status": "ok", "transferred_to": destination}
