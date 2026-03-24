"""WebSocket audio bridge for mod_audio_stream.

Receives binary PCM audio from FreeSWITCH via mod_audio_stream WebSocket,
routes through the voice pipeline, and sends TTS audio back.
Each WebSocket connection corresponds to one active call.
"""
import asyncio
import base64
import json
from dataclasses import dataclass
from typing import Optional

import numpy as np
import structlog
import websockets
import websockets.exceptions

from holler.core.voice.pipeline import VoicePipeline
from holler.core.voice.resampler import upsample_8k_to_16k

logger = structlog.get_logger()


@dataclass
class AudioBridgeConfig:
    host: str = "0.0.0.0"
    port: int = 8765
    sample_rate_in: int = 16000    # mod_audio_stream configured for 16k


class AudioBridge:
    """WebSocket server bridging FreeSWITCH audio to the voice pipeline."""

    def __init__(self, pipeline: VoicePipeline, config: Optional[AudioBridgeConfig] = None):
        self.pipeline = pipeline
        self.config = config or AudioBridgeConfig()
        self._server = None

    async def start(self) -> None:
        """Start the WebSocket server."""
        self._server = await websockets.serve(
            self._handle_connection,
            self.config.host,
            self.config.port,
        )
        logger.info("audio_bridge.started", host=self.config.host, port=self.config.port)

    async def stop(self) -> None:
        """Stop the WebSocket server."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("audio_bridge.stopped")

    async def _handle_connection(self, websocket) -> None:
        """Handle a single WebSocket connection from mod_audio_stream.

        Path format: /voice/{call_uuid}
        Compatible with websockets 13+ (path is websocket.path, not a separate arg).
        """
        # websockets 13+: path is in websocket.request.path
        path = websocket.request.path if hasattr(websocket, "request") and websocket.request else "/"
        call_uuid = path.strip("/").split("/")[-1]
        session_uuid = call_uuid  # Phase 1: session_uuid = call_uuid
        self.pipeline.create_session(call_uuid, session_uuid)

        logger.info("audio_bridge.connected", call_uuid=call_uuid, path=path)

        async def send_tts_audio(pcm_8k_bytes: bytes) -> None:
            """Send TTS audio back to FreeSWITCH via mod_audio_stream protocol."""
            payload = {
                "type": "streamAudio",
                "data": {
                    "audioDataType": "raw",
                    "sampleRate": 8000,
                    "audioData": base64.b64encode(pcm_8k_bytes).decode("ascii"),
                },
            }
            await websocket.send(json.dumps(payload))

        try:
            async for message in websocket:
                if isinstance(message, bytes):
                    # Binary frame: L16 PCM audio at configured sample rate
                    pcm_16k = np.frombuffer(message, dtype=np.int16).astype(np.float32) / 32768.0
                    await self.pipeline.process_audio_chunk(call_uuid, pcm_16k, send_tts_audio)
                elif isinstance(message, str):
                    # JSON metadata from mod_audio_stream (sent at connection start)
                    meta = json.loads(message)
                    logger.info("audio_bridge.metadata", call_uuid=call_uuid, meta=meta)
        except websockets.exceptions.ConnectionClosed:
            logger.info("audio_bridge.disconnected", call_uuid=call_uuid)
        finally:
            self.pipeline.remove_session(call_uuid)


async def start_audio_bridge(
    pipeline: VoicePipeline,
    config: Optional[AudioBridgeConfig] = None,
) -> AudioBridge:
    """Convenience function to create and start an audio bridge."""
    bridge = AudioBridge(pipeline, config)
    await bridge.start()
    return bridge
