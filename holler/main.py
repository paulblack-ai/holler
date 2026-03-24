"""Holler application entry point.

Boots the full Phase 2 integrated stack:
1. Load config (HollerConfig.from_env — includes pool, compliance, recording)
2. Create Redis client
3. Initialize voice pipeline (STT + TTS + LLM models)
4. Initialize data stores (NumberPool, ConsentDB, DNCList, AuditLog)
5. Set up compliance (USComplianceModule, JurisdictionRouter, ComplianceGateway)
6. Optionally create post-call transcription WhisperModel (CPU, int8)
7. Start audio bridge WebSocket server
8. Set up ESL event router with Phase 2 handlers
9. Start event router (blocks)

The outbound call path: DID checkout -> ComplianceGateway.originate_checked()
(with audit logging) -> ESL originate -> recording start on CHANNEL_ANSWER ->
DTMF opt-out handling during call -> recording stop on CHANNEL_HANGUP ->
post-call transcription (background task) -> DID release.

No outbound call can bypass the compliance gateway. The system is structurally
incapable of placing a non-compliant call.

Usage:
    python -m holler.main                          # Start server (wait for inbound calls)
    python -m holler.main --call +14155551234      # Originate outbound call
"""
import asyncio
import argparse
import time
import uuid
from typing import Dict, Optional
import structlog

from holler.config import HollerConfig
from holler.core.voice.pipeline import VoicePipeline
from holler.core.voice.audio_bridge import AudioBridge
from holler.core.freeswitch.esl import FreeSwitchESL
from holler.core.freeswitch.events import EventRouter
from holler.core.telecom.pool import NumberPool
from holler.core.telecom.session import TelecomSession
from holler.core.telecom.router import JurisdictionRouter
from holler.core.telecom.recording import recording_path, start_recording, stop_recording, transcribe_recording
from holler.core.compliance.gateway import ComplianceGateway, ComplianceBlockError
from holler.core.compliance.consent_db import ConsentDB
from holler.core.compliance.dnc import DNCList
from holler.core.compliance.audit import AuditLog
from holler.countries.us.module import USComplianceModule

logger = structlog.get_logger()


async def main(config: Optional[HollerConfig] = None, call_destination: Optional[str] = None):
    """Boot the Holler Phase 2 integrated voice pipeline stack."""
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

    # 2. Create Redis client for number pool
    import redis.asyncio as aioredis
    redis_client = aioredis.from_url(config.pool.redis_url, decode_responses=True)

    # 3. Initialize data stores
    pool = NumberPool(redis_client, pool_key=config.pool.pool_key)
    # Initialize pool with configured DIDs
    if config.pool.dids:
        dids = [d.strip() for d in config.pool.dids.split(",") if d.strip()]
        await pool.initialize(dids)

    consent_db = ConsentDB(config.compliance.consent_db_path)
    await consent_db.initialize()

    dnc_list = DNCList(config.compliance.dnc_db_path)
    await dnc_list.initialize()

    audit_log = AuditLog(config.compliance.audit_log_dir, config.compliance.audit_db_path)
    await audit_log.initialize()

    # 4. Set up compliance
    us_module = USComplianceModule(consent_db=consent_db, dnc_list=dnc_list)
    router = JurisdictionRouter()
    router.register("+1", us_module)

    gateway = ComplianceGateway(
        router=router,
        audit_log=audit_log,
        timeout=config.compliance.check_timeout_s,
    )

    # 5. Optionally create post-call transcription WhisperModel (CPU, int8)
    # Separate instance from live STT model — per Pitfall 6 in research.
    transcript_model = None
    if config.recording.transcript_enabled:
        try:
            from faster_whisper import WhisperModel
            transcript_model = WhisperModel(
                config.stt.model_name,
                device=config.recording.transcript_device,
                compute_type=config.recording.transcript_compute_type,
            )
            logger.info(
                "main.transcript_model_loaded",
                device=config.recording.transcript_device,
                compute_type=config.recording.transcript_compute_type,
            )
        except Exception as e:
            logger.warning("main.transcript_model_unavailable", error=str(e))

    # 6. Start audio bridge WebSocket server
    bridge = AudioBridge(pipeline, config.audio_bridge)
    await bridge.start()
    logger.info("main.audio_bridge_ready", port=config.audio_bridge.port)

    # 7. Set up ESL — single persistent connection for event-driven commands
    esl = FreeSwitchESL(config.esl)
    await esl.connect()

    # 8. Set up ESL event router with Phase 2 handlers
    event_router = EventRouter(config.esl)

    # Per-call telecom session tracking (parallel to EventRouter._active_calls)
    telecom_sessions: Dict[str, TelecomSession] = {}

    # --- Parse opt-out keywords from config ---
    opt_out_keywords = [kw.strip() for kw in config.compliance.opt_out_keywords.split(",") if kw.strip()]

    async def _post_call_transcript(session: TelecomSession, model) -> None:
        """Background task: transcribe recording after hangup."""
        try:
            json_path = await transcribe_recording(session.recording_path, model)
            session.transcript_path = json_path
            logger.info(
                "main.transcript_complete",
                call_uuid=session.call_uuid,
                json_path=json_path,
            )
        except Exception as e:
            logger.error(
                "main.transcript_error",
                call_uuid=session.call_uuid,
                error=str(e),
            )

    @event_router.on("CHANNEL_ANSWER")
    async def on_answer(event, call):
        call_uuid = event.get("Unique-ID", "")
        logger.info("main.call_answered", call_uuid=call_uuid)
        # Start recording if enabled
        if config.recording.enabled and call_uuid in telecom_sessions:
            session = telecom_sessions[call_uuid]
            rec_path = recording_path(config.recording.recordings_dir, call_uuid)
            session.recording_path = rec_path
            session.answered_at = time.monotonic()
            await start_recording(esl, call_uuid, rec_path)
            logger.info("main.recording_started", call_uuid=call_uuid, path=rec_path)

    @event_router.on("CHANNEL_HANGUP")
    async def on_hangup(event, call):
        call_uuid = event.get("Unique-ID", "")
        cause = event.get("Hangup-Cause", "UNKNOWN")
        logger.info("main.call_hungup", call_uuid=call_uuid, cause=cause)
        # Stop recording and fire background transcription
        if call_uuid in telecom_sessions:
            session = telecom_sessions[call_uuid]
            session.ended_at = time.monotonic()
            if session.recording_path:
                await stop_recording(esl, call_uuid, session.recording_path)
                # Fire background transcription (D-18)
                if config.recording.transcript_enabled and transcript_model:
                    asyncio.create_task(
                        _post_call_transcript(session, transcript_model)
                    )
            # Release DID back to pool
            await pool.release(session.did)
            logger.info("main.did_released", did=session.did, call_uuid=call_uuid)
            del telecom_sessions[call_uuid]
        pipeline.remove_session(call_uuid)

    @event_router.on("DTMF")
    async def on_dtmf(event, call):
        digit = event.get("DTMF-Digit", "")
        call_uuid = event.get("Unique-ID", "")
        if digit == config.compliance.opt_out_dtmf_key and call_uuid in telecom_sessions:
            session = telecom_sessions[call_uuid]
            await consent_db.record_optout(
                phone_number=session.destination,
                source="dtmf",
                call_uuid=call_uuid,
            )
            logger.info(
                "main.opt_out_dtmf",
                call_uuid=call_uuid,
                destination=session.destination,
                digit=digit,
            )
            await esl.hangup(call_uuid, "NORMAL_CLEARING")

    # 9. Optionally originate an outbound call
    if call_destination:
        asyncio.create_task(
            _originate_call(
                config=config,
                destination=call_destination,
                event_router=event_router,
                gateway=gateway,
                pool=pool,
                esl=esl,
                pipeline=pipeline,
                telecom_sessions=telecom_sessions,
            )
        )

    # 10. Start event router (blocks)
    logger.info("main.starting_event_router")
    try:
        await event_router.start()
    except KeyboardInterrupt:
        logger.info("main.shutting_down")
    finally:
        await bridge.stop()
        await esl.disconnect()
        await consent_db.close()
        await dnc_list.close()
        await audit_log.close()
        await redis_client.aclose()
        logger.info("main.shutdown_complete")


async def _originate_call(
    config: HollerConfig,
    destination: str,
    event_router: EventRouter,
    gateway: ComplianceGateway,
    pool: NumberPool,
    esl: FreeSwitchESL,
    pipeline: VoicePipeline,
    telecom_sessions: Dict[str, TelecomSession],
) -> None:
    """Originate an outbound call through the compliance gateway.

    Outbound call path:
    DID checkout -> ComplianceGateway.originate_checked() (with audit logging)
    -> ESL originate -> register call in event router -> create voice session
    -> start audio stream

    Per D-03: DID must be checked out before originate.
    Per D-07: All calls must go through ComplianceGateway.originate_checked().
    """
    await asyncio.sleep(1)  # Wait for event router to be ready
    session_uuid = str(uuid.uuid4())

    # D-03: Acquire DID first — no call can originate without a checked-out DID
    did = await pool.checkout()

    session = TelecomSession(
        session_uuid=session_uuid,
        call_uuid="",  # Set by gateway after originate
        did=did,
        destination=destination,
        jurisdiction="",  # Set by router during compliance check
        started_at=time.monotonic(),
    )

    try:
        # D-07: All outbound calls go through compliance gateway (no direct esl.originate)
        call_uuid = await gateway.originate_checked(esl, pool, session)
        session.call_uuid = call_uuid
        telecom_sessions[call_uuid] = session
        event_router.register_call(
            call_uuid, session_uuid, direction="outbound", destination=destination
        )

        # Create voice session and attach to telecom session
        voice_session = pipeline.create_session(call_uuid, session_uuid)
        session.voice_session = voice_session

        # Start audio stream
        ws_url = f"{config.esl.audio_stream_ws_base}/{call_uuid}"
        await esl.start_audio_stream(call_uuid, ws_url)
        logger.info(
            "main.outbound_call_started",
            destination=destination,
            call_uuid=call_uuid,
            did=did,
        )
    except ComplianceBlockError as e:
        logger.warning(
            "main.call_blocked",
            destination=destination,
            did=did,
            reason=str(e),
        )
        # Note: pool.release() is called inside ComplianceGateway.originate_checked()
        # when it raises ComplianceBlockError — no double-release needed.


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
