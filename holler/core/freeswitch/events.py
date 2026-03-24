"""FreeSWITCH ESL event router for call lifecycle management.

Subscribes to FreeSWITCH events (CHANNEL_ANSWER, CHANNEL_HANGUP, etc.)
and dispatches to registered async handlers. Uses Genesis Consumer mode.
Manages call state tracking for active calls.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Awaitable, Any, Dict, List, Optional
import structlog

logger = structlog.get_logger()


class CallState(Enum):
    ORIGINATING = "originating"    # Originate sent, waiting for answer
    RINGING = "ringing"            # Remote side ringing
    ANSWERED = "answered"          # Call connected
    STREAMING = "streaming"        # Audio stream active
    HUNGUP = "hungup"              # Call ended


@dataclass
class ActiveCall:
    """Tracks state for an active call."""
    call_uuid: str
    session_uuid: str
    state: CallState = CallState.ORIGINATING
    direction: str = "outbound"      # "outbound" or "inbound"
    destination: str = ""
    caller_id: str = ""
    answer_time: Optional[float] = None
    hangup_time: Optional[float] = None
    hangup_cause: str = ""


# Type alias for event handler callbacks
EventHandler = Callable[[dict, Optional["ActiveCall"]], Awaitable[None]]


class EventRouter:
    """Routes FreeSWITCH ESL events to registered handlers.

    Usage:
        router = EventRouter(ESLConfig())

        @router.on("CHANNEL_ANSWER")
        async def handle_answer(event: dict, call: ActiveCall | None):
            ...

        @router.on("CHANNEL_HANGUP")
        async def handle_hangup(event: dict, call: ActiveCall | None):
            ...

        await router.start()  # Blocks, listening for events
    """

    def __init__(self, config):
        from holler.core.freeswitch.esl import ESLConfig
        self.config = config if isinstance(config, ESLConfig) else ESLConfig()
        self._handlers: Dict[str, List[EventHandler]] = {}
        self._active_calls: Dict[str, ActiveCall] = {}
        self._consumer = None

    def on(self, event_name: str):
        """Decorator to register an event handler."""
        def decorator(func: EventHandler):
            self._handlers.setdefault(event_name, []).append(func)
            return func
        return decorator

    def register_call(self, call_uuid: str, session_uuid: str, direction: str = "outbound", destination: str = "") -> ActiveCall:
        """Register a new call for tracking. Call this after originate."""
        call = ActiveCall(
            call_uuid=call_uuid,
            session_uuid=session_uuid,
            direction=direction,
            destination=destination,
        )
        self._active_calls[call_uuid] = call
        logger.info("events.call_registered", call_uuid=call_uuid, direction=direction)
        return call

    def get_call(self, call_uuid: str) -> Optional[ActiveCall]:
        """Look up an active call by UUID."""
        return self._active_calls.get(call_uuid)

    def remove_call(self, call_uuid: str) -> None:
        """Remove a call from tracking."""
        self._active_calls.pop(call_uuid, None)

    async def _dispatch(self, event_name: str, event: dict) -> None:
        """Dispatch an event to all registered handlers."""
        call_uuid = event.get("Unique-ID", "")
        call = self._active_calls.get(call_uuid)

        # Update call state based on event
        if call:
            import time
            if event_name == "CHANNEL_ANSWER":
                call.state = CallState.ANSWERED
                call.answer_time = time.monotonic()
            elif event_name == "CHANNEL_HANGUP":
                call.state = CallState.HUNGUP
                call.hangup_time = time.monotonic()
                call.hangup_cause = event.get("Hangup-Cause", "UNKNOWN")

        handlers = self._handlers.get(event_name, [])
        for handler in handlers:
            try:
                await handler(event, call)
            except Exception as e:
                logger.error("events.handler_error", event=event_name, call_uuid=call_uuid, error=str(e))

        logger.debug("events.dispatched", event=event_name, call_uuid=call_uuid, handlers=len(handlers))

    async def start(self) -> None:
        """Start the event consumer. Blocks while listening for events."""
        from genesis import Consumer

        self._consumer = Consumer(self.config.host, self.config.port, self.config.password)

        # Register all event types we have handlers for
        for event_name in self._handlers:
            @self._consumer.handle(event_name)
            async def make_handler(evt, name=event_name):
                await self._dispatch(name, evt)

        logger.info("events.starting", events=list(self._handlers.keys()))
        await self._consumer.start()

    async def stop(self) -> None:
        """Stop the event consumer."""
        if self._consumer:
            # Genesis Consumer doesn't have a formal stop — cancel via task
            logger.info("events.stopped")
