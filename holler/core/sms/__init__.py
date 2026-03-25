"""holler.core.sms — SMPP messaging layer.

Provides the SMS send/receive/delivery-status capabilities for the Holler
agent interface. Uses aiosmpplib as a persistent async ESME connection.

Public API:
    SMSClient   — async SMPP ESME client (deferred init pattern)
    SMSConfig   — dataclass: smsc_host, smsc_port, system_id, password, source_address
    HollerHook  — aiosmpplib hook: delivery receipts + inbound SMS routing
    SMSSession  — dataclass: per-conversation SMS thread state
"""

from holler.core.sms.client import SMSClient, SMSConfig
from holler.core.sms.hook import HollerHook
from holler.core.sms.session import SMSSession

__all__ = ["SMSClient", "SMSConfig", "HollerHook", "SMSSession"]
