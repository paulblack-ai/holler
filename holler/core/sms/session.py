"""SMS session state.

SMSSession tracks the state of an inbound SMS conversation: who sent it,
which number it came in on, and the message history.

Unlike TelecomSession (which is call-scoped), SMSSession is
conversation-scoped — it persists across multiple message exchanges
in a single interaction thread.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import List


@dataclass
class SMSSession:
    """Per-conversation SMS session state.

    Tracks the sender, destination DID, and message history for a single
    SMS interaction thread. Intended to be stored in the number pool's
    session map and keyed by session_uuid.

    Fields:
        session_uuid: Unique ID for this SMS conversation thread.
        sender: E.164 originating phone number (the human or remote agent).
        destination: E.164 destination number (our DID that received the SMS).
        messages: Ordered list of messages in the thread. Each entry is a dict
            with keys: "role" ("user" | "agent"), "text" (str), "timestamp" (float).
        created_at: Monotonic timestamp (time.monotonic()) when the session began.
    """

    session_uuid: str
    sender: str           # E.164 originator
    destination: str      # E.164 recipient / our DID
    created_at: float     # time.monotonic() when session started

    # Message history — each dict has {"role": str, "text": str, "timestamp": float}
    messages: List[dict] = field(default_factory=list)
