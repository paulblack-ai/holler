"""SMS client — async SMPP ESME connection with delivery status tracking.

SMSClient manages a persistent aiosmpplib ESME connection to an SMSC.
It follows the deferred initialization pattern (initialize() not __init__)
used throughout the Holler codebase — the ESME connection is established
in initialize(), not in __init__().

Per D-05 (CONTEXT.md): aiosmpplib is the async SMPP client.
Per D-06 (CONTEXT.md): SMSClient follows the same deferred-init pattern as
STTEngine, TTSEngine, and FreeSwitchESL.

The delivery status store (a plain dict) is shared with HollerHook so that
delivery receipts arriving on the SMSC connection automatically update
the queryable status without polling.

Usage:
    client = SMSClient(SMSConfig(smsc_host="10.0.0.1", system_id="myagent"))
    await client.initialize(inbound_handler=my_handler)
    await client.send("+15550001234", "Hello from agent", log_id="msg-abc")
    status = client.get_status("msg-abc")  # "queued", "delivered", etc.
    await client.stop()
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable, Optional

import structlog

from holler.core.sms.hook import HollerHook

if TYPE_CHECKING:
    from aiosmpplib import ESME, SubmitSm, PhoneNumber

logger = structlog.get_logger(__name__)


@dataclass
class SMSConfig:
    """Configuration for the SMPP ESME connection.

    Defaults target a local SMSC (e.g. Jasmin running on the same host).

    Fields:
        smsc_host: SMSC hostname or IP address.
        smsc_port: SMSC TCP port (SMPP default is 2775).
        system_id: ESME system ID — used for SMSC authentication.
        password: SMSC authentication password.
        source_address: Default originating E.164 address for outbound SMS.
    """

    smsc_host: str = "127.0.0.1"
    smsc_port: int = 2775
    system_id: str = "holler"
    password: str = ""
    source_address: str = ""


class SMSClient:
    """Async SMPP ESME client with delivery status tracking and inbound routing.

    The ESME connection is established in initialize(), not __init__(), so the
    object can be constructed before the event loop is running or before the
    SMSC is available.

    Delivery status is tracked in an in-memory dict keyed by log_id. The
    HollerHook updates this dict when delivery receipts arrive from the SMSC.
    """

    def __init__(self, config: Optional[SMSConfig] = None) -> None:
        """Initialize the SMSClient without connecting.

        Args:
            config: SMSConfig with SMSC connection parameters.
                    Defaults to SMSConfig() if not provided.
        """
        self.config = config or SMSConfig()
        self._delivery_store: dict = {}
        self._esme = None
        self._task: Optional[asyncio.Task] = None

    async def initialize(self, inbound_handler: Optional[Callable] = None) -> None:
        """Connect to the SMSC and start the ESME event loop.

        Creates HollerHook with the shared delivery store, constructs the
        aiosmpplib ESME, and starts the ESME as an asyncio background task.

        Args:
            inbound_handler: Optional async callable(sender: str, text: str)
                invoked when a non-receipt inbound SMS arrives on this ESME
                connection.
        """
        # Runtime import — aiosmpplib may not be installed in all environments
        from aiosmpplib import ESME  # noqa: F401

        hook = HollerHook(self._delivery_store, inbound_handler)

        self._esme = ESME(
            system_id=self.config.system_id,
            password=self.config.password,
            host=self.config.smsc_host,
            port=self.config.smsc_port,
            hook=hook,
        )

        self._task = asyncio.create_task(self._esme.start())
        logger.info(
            "sms.client.initialized",
            smsc_host=self.config.smsc_host,
            smsc_port=self.config.smsc_port,
            system_id=self.config.system_id,
        )

    async def send(self, destination: str, message: str, log_id: str) -> None:
        """Send an outbound SMS via the SMPP ESME connection.

        Enqueues a SubmitSm PDU to the ESME broker. The delivery store is
        immediately updated to "queued" — the status will transition to
        "delivered", "failed", etc. when a delivery receipt arrives.

        Args:
            destination: E.164 destination phone number.
            message: UTF-8 message text.
            log_id: Unique identifier for this message (used as the SMPP
                    log_id and as the key in the delivery store).
        """
        from aiosmpplib import SubmitSm, PhoneNumber  # noqa: F401

        msg = SubmitSm(
            short_message=message,
            source=PhoneNumber(self.config.source_address),
            destination=PhoneNumber(destination),
            log_id=log_id,
        )
        await self._esme.broker.enqueue(msg)
        self._delivery_store[log_id] = "queued"
        logger.debug("sms.queued", log_id=log_id, destination=destination)

    def get_status(self, log_id: str) -> str:
        """Return the current delivery status for a message.

        Args:
            log_id: Message identifier previously passed to send().

        Returns:
            Status string: "queued", "delivered", "failed", "expired",
            "accepted", or "unknown" if log_id has not been seen.
        """
        return self._delivery_store.get(log_id, "unknown")

    async def stop(self) -> None:
        """Stop the ESME connection and cancel the background task."""
        if self._esme is not None:
            await self._esme.stop()
            logger.info("sms.client.stopped")
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass
            self._task = None
