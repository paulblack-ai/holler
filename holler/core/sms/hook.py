"""SMPP hook for HollerHook — delivery receipt and inbound SMS routing.

HollerHook is the aiosmpplib AbstractHook implementation used by SMSClient's
ESME connection. It handles two event types:
  - Delivery receipts (DeliverSm with is_receipt() == True): update the
    delivery status store.
  - Inbound SMS (DeliverSm with is_receipt() == False): route to the
    inbound handler callback.

Per D-08 (CONTEXT.md): The SMPP hook pattern mirrors the ESL hook pattern
used in the voice pipeline — a single callback interface for all inbound events.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Callable, Optional

import structlog

if TYPE_CHECKING:
    from aiosmpplib import AbstractHook, DeliverSm

logger = structlog.get_logger(__name__)

# Status mapping: SMPP stat field -> internal status string
# Per SMPP 3.4 spec §5.2.28 message_state
_RECEIPT_STAT_MAP = {
    "DELIVRD": "delivered",
    "EXPIRED": "expired",
    "UNDELIV": "failed",
    "REJECTD": "failed",
    "ACCEPTD": "accepted",
}


def _get_abstract_hook_base():
    """Import AbstractHook at runtime — avoids hard import error when aiosmpplib not installed."""
    from aiosmpplib import AbstractHook
    return AbstractHook


class HollerHook:
    """SMPP event hook: delivery receipts -> status store, inbound SMS -> handler.

    Passed to the ESME constructor via hook=HollerHook(...). Receives all
    inbound SMPP PDUs from the SMSC.

    Note: This does not inherit from AbstractHook at class definition time
    to avoid a hard import of aiosmpplib at module load. The duck-typing
    approach is safe because aiosmpplib calls the hook via protocol interface,
    not isinstance checks.

    Args:
        delivery_store: Shared dict mapping log_id -> status string.
            Updated in-place when delivery receipts arrive.
        inbound_handler: Optional async callable(sender: str, text: str)
            invoked for non-receipt inbound SMS messages.
    """

    def __init__(
        self,
        delivery_store: dict,
        inbound_handler: Optional[Callable] = None,
    ) -> None:
        self._store = delivery_store
        self._inbound_handler = inbound_handler

    async def sending(self, smpp_message, pdu, client_id) -> None:
        """Called before a message is sent to the SMSC. Debug log only."""
        logger.debug(
            "sms.sending",
            log_id=getattr(smpp_message, "log_id", None),
            client_id=client_id,
        )

    async def received(self, smpp_message, pdu, client_id) -> None:
        """Route inbound SMPP PDU to delivery receipt handler or inbound SMS handler.

        Args:
            smpp_message: Parsed aiosmpplib message object (DeliverSm or other).
            pdu: Raw SMPP PDU bytes (unused — smpp_message is preferred).
            client_id: ESME client identifier string.
        """
        from aiosmpplib import DeliverSm

        if not isinstance(smpp_message, DeliverSm):
            logger.debug("sms.received.unhandled_type", type=type(smpp_message).__name__)
            return

        if smpp_message.is_receipt():
            # Delivery receipt: update status store
            stat = self._extract_stat(smpp_message)
            status = _RECEIPT_STAT_MAP.get(stat, "unknown")
            log_id = smpp_message.log_id
            if log_id is not None:
                self._store[log_id] = status
                logger.debug(
                    "sms.receipt",
                    log_id=log_id,
                    stat=stat,
                    status=status,
                )
        else:
            # Inbound SMS: route to handler
            sender = str(smpp_message.source)
            text = smpp_message.short_message
            logger.debug("sms.inbound", sender=sender, text_len=len(text or ""))
            if self._inbound_handler is not None:
                await self._inbound_handler(sender, text)

    async def send_error(self, smpp_message, error, client_id) -> None:
        """Called when a send operation fails at the SMPP layer."""
        logger.error(
            "sms.send_error",
            log_id=getattr(smpp_message, "log_id", None),
            error=str(error),
            client_id=client_id,
        )

    def _extract_stat(self, smpp_message) -> str:
        """Extract the stat field from a delivery receipt's short_message text.

        Delivery receipt format per SMPP 3.4 spec §B.1:
          id:XXXX sub:001 dlvrd:001 ... stat:DELIVRD err:000 text:...

        Returns the stat value or empty string if not found.
        """
        text = smpp_message.short_message or ""
        for part in text.split():
            if part.startswith("stat:"):
                return part[5:]
        return ""
