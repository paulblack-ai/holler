"""FreeSWITCH ESL client wrapper using Genesis.

Provides call control operations via ESL inbound mode (D-02).
Uses Genesis library (D-01) for asyncio-native ESL communication.
All commands go through a persistent connection to ESL port 8021.
"""
from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Optional
import structlog

logger = structlog.get_logger()


@dataclass
class ESLConfig:
    host: str = "127.0.0.1"
    port: int = 8021
    password: str = "ClueCon"
    audio_stream_ws_base: str = "ws://127.0.0.1:8765/voice"


class FreeSwitchESL:
    """Async FreeSWITCH ESL client for call control.

    Usage:
        async with FreeSwitchESL(config) as esl:
            call_uuid = await esl.originate("+14155551234", session_uuid)
            await esl.start_audio_stream(call_uuid, f"{config.audio_stream_ws_base}/{call_uuid}")
            await esl.hangup(call_uuid)
    """

    def __init__(self, config: Optional[ESLConfig] = None):
        self.config = config or ESLConfig()
        self._client = None

    def _make_inbound(self):
        """Factory method for Genesis Inbound client. Separated for testability."""
        from genesis import Inbound
        return Inbound(self.config.host, self.config.port, self.config.password)

    async def connect(self) -> None:
        """Connect to FreeSWITCH ESL and verify server is UP."""
        self._client = self._make_inbound()
        await self._client.connect()
        status = await self._client.send("api status")
        if "UP" not in str(status):
            raise RuntimeError(f"FreeSWITCH not ready: {status}")
        logger.info("esl.connected", host=self.config.host, port=self.config.port)

    async def disconnect(self) -> None:
        """Close ESL connection."""
        if self._client:
            await self._client.close()
            self._client = None
            logger.info("esl.disconnected")

    async def __aenter__(self):
        await self.connect()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()

    async def originate(self, destination: str, session_uuid: str, gateway: str = "sip_trunk") -> str:
        """Originate an outbound call. Returns FreeSWITCH call UUID.

        Args:
            destination: E.164 phone number (e.g., "+14155551234")
            session_uuid: Application session ID to correlate events
            gateway: SIP gateway name (default: "sip_trunk")

        Returns:
            FreeSWITCH call UUID string

        Raises:
            RuntimeError: If originate command fails
        """
        cmd = (
            f"api originate "
            f"{{session_uuid={session_uuid},ignore_early_media=true}}"
            f"sofia/gateway/{gateway}/{destination} "
            f"&park()"
        )
        result = await self._client.send(cmd)
        result_str = str(result).strip()
        if not result_str.startswith("+OK"):
            raise RuntimeError(f"Originate failed: {result_str}")
        call_uuid = result_str.split()[-1]
        logger.info("esl.originate", destination=destination, call_uuid=call_uuid, session_uuid=session_uuid)
        return call_uuid

    async def hangup(self, call_uuid: str, cause: str = "NORMAL_CLEARING") -> None:
        """Terminate a call by UUID."""
        result = await self._client.send(f"api uuid_kill {call_uuid} {cause}")
        logger.info("esl.hangup", call_uuid=call_uuid, cause=cause, result=str(result).strip())

    async def start_audio_stream(self, call_uuid: str, ws_url: str) -> None:
        """Start mod_audio_stream for a call, connecting to the given WebSocket URL.

        Args:
            call_uuid: FreeSWITCH call UUID
            ws_url: WebSocket URL (e.g., "ws://127.0.0.1:8765/voice/uuid-here")
        """
        result = await self._client.send(f"api uuid_audio_stream {call_uuid} start {ws_url} mono 16k")
        logger.info("esl.audio_stream_start", call_uuid=call_uuid, ws_url=ws_url, result=str(result).strip())

    async def stop_audio_stream(self, call_uuid: str) -> None:
        """Stop mod_audio_stream for a call."""
        result = await self._client.send(f"api uuid_audio_stream {call_uuid} stop")
        logger.info("esl.audio_stream_stop", call_uuid=call_uuid, result=str(result).strip())

    async def send_raw(self, command: str) -> str:
        """Send a raw ESL command. Returns response string."""
        result = await self._client.send(command)
        return str(result).strip()
