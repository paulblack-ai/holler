"""Holler application entry point.

Boots the full voice pipeline stack:
1. Initialize voice pipeline (STT + TTS + LLM models)
2. Start audio bridge WebSocket server (receives audio from FreeSWITCH)
3. Start ESL event router (handles call lifecycle events)
4. Optionally originate an outbound call

Usage:
    python -m holler.main                          # Start server (wait for inbound calls)
    python -m holler.main --call +14155551234      # Originate outbound call
"""
import asyncio
import argparse
import uuid
from typing import Optional
import structlog

from holler.config import HollerConfig
from holler.core.voice.pipeline import VoicePipeline
from holler.core.voice.audio_bridge import AudioBridge
from holler.core.freeswitch.esl import FreeSwitchESL
from holler.core.freeswitch.events import EventRouter

logger = structlog.get_logger()


async def main(config: Optional[HollerConfig] = None, call_destination: Optional[str] = None):
    """Boot the Holler voice pipeline stack."""
    config = config or HollerConfig.from_env()

    # 1. Initialize voice pipeline (loads STT/TTS/LLM models)
    logger.info("main.initializing_pipeline")
    pipeline = VoicePipeline(
        stt_config=config.stt,
        tts_config=config.tts,
        llm_config=config.llm,
        vad_config=config.vad,
    )
    await pipeline.initialize()

    # 2. Start audio bridge WebSocket server
    bridge = AudioBridge(pipeline, config.audio_bridge)
    await bridge.start()
    logger.info("main.audio_bridge_ready", port=config.audio_bridge.port)

    # 3. Set up ESL event router
    event_router = EventRouter(config.esl)

    @event_router.on("CHANNEL_ANSWER")
    async def on_answer(event, call):
        call_uuid = event.get("Unique-ID", "")
        logger.info("main.call_answered", call_uuid=call_uuid)

    @event_router.on("CHANNEL_HANGUP")
    async def on_hangup(event, call):
        call_uuid = event.get("Unique-ID", "")
        cause = event.get("Hangup-Cause", "UNKNOWN")
        pipeline.remove_session(call_uuid)
        logger.info("main.call_hungup", call_uuid=call_uuid, cause=cause)

    # 4. Optionally originate an outbound call
    if call_destination:
        asyncio.create_task(_originate_call(config, call_destination, event_router))

    # 5. Start event router (blocks)
    logger.info("main.starting_event_router")
    try:
        await event_router.start()
    except KeyboardInterrupt:
        logger.info("main.shutting_down")
    finally:
        await bridge.stop()


async def _originate_call(config: HollerConfig, destination: str, event_router: EventRouter):
    """Originate an outbound call after a short delay for setup."""
    await asyncio.sleep(1)  # Wait for event router to be ready
    session_uuid = str(uuid.uuid4())

    async with FreeSwitchESL(config.esl) as esl:
        call_uuid = await esl.originate(destination, session_uuid)
        event_router.register_call(call_uuid, session_uuid, direction="outbound", destination=destination)

        # Start audio stream for this call
        ws_url = f"{config.esl.audio_stream_ws_base}/{call_uuid}"
        await esl.start_audio_stream(call_uuid, ws_url)
        logger.info("main.outbound_call_started", destination=destination, call_uuid=call_uuid)


def cli():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="Holler Voice Pipeline")
    parser.add_argument("--call", type=str, help="Originate outbound call to this number (E.164)")
    args = parser.parse_args()

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.dev.ConsoleRenderer(),
        ],
    )

    asyncio.run(main(call_destination=args.call))


if __name__ == "__main__":
    cli()
