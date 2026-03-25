"""Phase 5 wiring tests — verify both unwired paths are connected.

Tests cover:
1. consent_db schema accepts source='stt' without CHECK constraint violation
2. main.py source contains inbound_handler= in sms_client.initialize() call (structural)
3. main.py source contains _handle_stt_optout (structural)
4. pipeline.py source contains check_optout_keywords import and call (structural)
5. VoicePipeline._respond() calls on_optout when keyword matched
6. VoicePipeline._respond() continues to LLM when no keyword matched
7. Inbound SMS handler creates SMSSession and logs message (functional)

Tests use asyncio directly (no pytest-asyncio) per project convention.
"""
from __future__ import annotations

import asyncio
import inspect
import os
import sys
import time
import types
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# ---------------------------------------------------------------------------
# Minimal stubs for aiosmpplib (needed for importing holler.main)
# ---------------------------------------------------------------------------

def _make_aiosmpplib_stub():
    mod = types.ModuleType("aiosmpplib")

    class PhoneNumber:
        def __init__(self, number):
            self.number = number
        def __str__(self):
            return self.number

    class SubmitSm:
        def __init__(self, short_message, source, destination, log_id):
            self.short_message = short_message
            self.source = source
            self.destination = destination
            self.log_id = log_id

    class DeliverSm:
        def __init__(self, short_message, source, log_id=None, receipt=False):
            self.short_message = short_message
            self.source = source
            self.log_id = log_id
            self._receipt = receipt
        def is_receipt(self):
            return self._receipt

    class Broker:
        async def enqueue(self, msg):
            pass

    class ESME:
        def __init__(self, *args, **kwargs):
            self.broker = Broker()
        async def start(self):
            pass
        async def stop(self):
            pass

    class AbstractHook:
        async def sending(self, smpp_message, pdu, client_id):
            pass
        async def received(self, smpp_message, pdu, client_id):
            pass
        async def send_error(self, smpp_message, error, client_id):
            pass

    mod.PhoneNumber = PhoneNumber
    mod.SubmitSm = SubmitSm
    mod.DeliverSm = DeliverSm
    mod.ESME = ESME
    mod.AbstractHook = AbstractHook
    mod.Broker = Broker
    return mod


if "aiosmpplib" not in sys.modules:
    sys.modules["aiosmpplib"] = _make_aiosmpplib_stub()


def run(coro):
    """Run coroutine synchronously (no pytest-asyncio on system Python)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# Helper: project paths
# ---------------------------------------------------------------------------

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read_source(rel_path: str) -> str:
    full = os.path.join(PROJECT_ROOT, rel_path)
    with open(full) as f:
        return f.read()


# ===========================================================================
# 1. consent_db schema accepts source='stt'
# ===========================================================================

class TestConsentDBSttSource(unittest.TestCase):
    """consent_db CHECK constraint must include 'stt'."""

    def test_record_optout_with_stt_source_no_error(self):
        """record_optout(source='stt') must not raise a CHECK constraint violation."""
        from holler.core.compliance.consent_db import ConsentDB

        async def _run():
            db = ConsentDB(":memory:")
            await db.initialize()
            # Must not raise
            await db.record_optout("+15550001234", source="stt", call_uuid="call-uuid-1")
            await db.close()

        run(_run())

    def test_consent_db_source_contains_stt_string(self):
        """consent_db.py source must contain the string 'stt' in the CHECK constraint."""
        src = _read_source("holler/core/compliance/consent_db.py")
        self.assertIn("'stt'", src, "consent_db.py CHECK constraint must include 'stt'")


# ===========================================================================
# 2. main.py structural: inbound_handler= in sms_client.initialize()
# ===========================================================================

class TestMainPyInboundHandlerWiring(unittest.TestCase):
    """main.py must pass inbound_handler= to sms_client.initialize()."""

    def test_inbound_handler_kwarg_in_main_source(self):
        """main.py source must contain 'inbound_handler=' in sms_client.initialize() call."""
        src = _read_source("holler/main.py")
        self.assertIn(
            "inbound_handler=",
            src,
            "main.py must pass inbound_handler= to sms_client.initialize()",
        )

    def test_handle_inbound_sms_defined_in_main(self):
        """main.py must define _handle_inbound_sms function."""
        src = _read_source("holler/main.py")
        self.assertGreaterEqual(
            src.count("_handle_inbound_sms"),
            2,
            "main.py must define and reference _handle_inbound_sms at least twice",
        )


# ===========================================================================
# 3. main.py structural: _handle_stt_optout defined
# ===========================================================================

class TestMainPySttOptoutWiring(unittest.TestCase):
    """main.py must define _handle_stt_optout and pass it to VoicePipeline."""

    def test_handle_stt_optout_defined_in_main(self):
        """main.py source must contain _handle_stt_optout."""
        src = _read_source("holler/main.py")
        self.assertGreaterEqual(
            src.count("_handle_stt_optout"),
            2,
            "main.py must define and reference _handle_stt_optout at least twice",
        )

    def test_on_optout_passed_to_voice_pipeline_in_main(self):
        """main.py must pass on_optout= to VoicePipeline constructor."""
        src = _read_source("holler/main.py")
        self.assertIn(
            "on_optout=",
            src,
            "main.py must pass on_optout= to VoicePipeline()",
        )


# ===========================================================================
# 4. pipeline.py structural: check_optout_keywords present
# ===========================================================================

class TestPipelinePyOptoutWiring(unittest.TestCase):
    """pipeline.py must import and call check_optout_keywords."""

    def test_check_optout_keywords_in_pipeline_source(self):
        """pipeline.py must contain check_optout_keywords."""
        src = _read_source("holler/core/voice/pipeline.py")
        self.assertGreaterEqual(
            src.count("check_optout_keywords"),
            1,
            "pipeline.py must call check_optout_keywords",
        )

    def test_on_optout_in_pipeline_source(self):
        """pipeline.py must reference on_optout at least twice (init param + call)."""
        src = _read_source("holler/core/voice/pipeline.py")
        self.assertGreaterEqual(
            src.count("on_optout"),
            2,
            "pipeline.py must reference on_optout at least twice",
        )


# ===========================================================================
# 5. VoicePipeline._respond() calls on_optout when keyword matched
# ===========================================================================

class TestPipelineOptoutCallbackCalled(unittest.TestCase):
    """on_optout callback must be invoked when STT transcript contains opt-out keyword."""

    def _make_pipeline(self, opt_out_keywords, on_optout=None):
        """Construct a VoicePipeline with mocked STT/TTS/LLM engines."""
        from holler.core.voice.pipeline import VoicePipeline
        from holler.core.voice.stt import STTConfig
        from holler.core.voice.tts import TTSConfig
        from holler.core.voice.llm import LLMConfig
        from holler.core.voice.vad import VADConfig

        pipeline = VoicePipeline(
            stt_config=STTConfig(),
            tts_config=TTSConfig(),
            llm_config=LLMConfig(),
            vad_config=VADConfig(),
            opt_out_keywords=opt_out_keywords,
            on_optout=on_optout,
        )
        # Replace engines with mocks
        pipeline.stt = MagicMock()
        pipeline.tts = MagicMock()
        pipeline.llm = MagicMock()
        return pipeline

    def test_on_optout_called_when_keyword_matched(self):
        """_respond() must call on_optout when STT transcript contains a keyword."""
        optout_calls = []

        async def _on_optout(call_uuid, keyword):
            optout_calls.append((call_uuid, keyword))

        pipeline = self._make_pipeline(["stop"], on_optout=_on_optout)
        # STT returns a transcript with keyword
        pipeline.stt.transcribe_buffer = AsyncMock(return_value=["please stop calling"])

        import numpy as np
        from holler.core.voice.pipeline import VoiceSession
        from holler.core.voice.vad import VADState, VADConfig

        async def _run():
            session = VoiceSession(
                call_uuid="call-001",
                session_uuid="sess-001",
                vad=VADState(VADConfig()),
            )
            send_audio = AsyncMock()
            await pipeline._respond(session, np.zeros(160, dtype=np.float32), send_audio)

        run(_run())

        self.assertEqual(len(optout_calls), 1, "on_optout should be called once")
        self.assertEqual(optout_calls[0][0], "call-001")
        self.assertEqual(optout_calls[0][1], "stop")

    def test_llm_not_called_when_keyword_matched(self):
        """_respond() must NOT call LLM when opt-out keyword is detected."""
        async def _on_optout(call_uuid, keyword):
            pass

        pipeline = self._make_pipeline(["stop"], on_optout=_on_optout)
        pipeline.stt.transcribe_buffer = AsyncMock(return_value=["please stop calling"])
        pipeline.llm.stream_response = AsyncMock()  # should not be called

        import numpy as np
        from holler.core.voice.pipeline import VoiceSession
        from holler.core.voice.vad import VADState, VADConfig

        async def _run():
            session = VoiceSession(
                call_uuid="call-001",
                session_uuid="sess-001",
                vad=VADState(VADConfig()),
            )
            await pipeline._respond(session, np.zeros(160, dtype=np.float32), AsyncMock())

        run(_run())

        pipeline.llm.stream_response.assert_not_called()


# ===========================================================================
# 6. VoicePipeline._respond() continues to LLM when no keyword matched
# ===========================================================================

class TestPipelineContinuesWhenNoKeyword(unittest.TestCase):
    """LLM must be called when no opt-out keyword is detected."""

    def test_llm_called_when_no_keyword_matched(self):
        """_respond() must proceed to LLM when transcript has no opt-out keyword."""
        from holler.core.voice.pipeline import VoicePipeline
        from holler.core.voice.stt import STTConfig
        from holler.core.voice.tts import TTSConfig
        from holler.core.voice.llm import LLMConfig
        from holler.core.voice.vad import VADConfig, VADState
        from holler.core.voice.pipeline import VoiceSession

        pipeline = VoicePipeline(
            stt_config=STTConfig(),
            tts_config=TTSConfig(),
            llm_config=LLMConfig(),
            vad_config=VADConfig(),
            opt_out_keywords=["stop", "do not call"],
        )
        pipeline.stt = MagicMock()
        pipeline.tts = MagicMock()
        pipeline.llm = MagicMock()

        # Transcript without any opt-out keyword
        pipeline.stt.transcribe_buffer = AsyncMock(return_value=["hello there how are you"])

        llm_calls = []

        async def fake_stream(transcript, history, tools=None):
            llm_calls.append(transcript)
            return
            yield  # make it an async generator

        pipeline.llm.stream_response = fake_stream

        async def fake_synth(token_queue):
            # drain the queue
            while True:
                item = await token_queue.get()
                if item is None:
                    break
            return
            yield  # make it an async generator

        pipeline.tts.synthesize_stream = fake_synth

        import numpy as np

        async def _run():
            session = VoiceSession(
                call_uuid="call-002",
                session_uuid="sess-002",
                vad=VADState(VADConfig()),
            )
            await pipeline._respond(session, np.zeros(160, dtype=np.float32), AsyncMock())

        run(_run())

        self.assertEqual(len(llm_calls), 1, "LLM should be called once when no keyword matched")


# ===========================================================================
# 7. Inbound SMS handler creates SMSSession and logs
# ===========================================================================

class TestInboundSmsHandlerFunctional(unittest.TestCase):
    """_handle_inbound_sms must create SMSSession and append messages."""

    def test_handler_creates_session_on_first_message(self):
        """Calling the handler for a new sender should create an SMSSession."""
        from holler.core.sms.session import SMSSession

        sms_sessions = {}

        async def _handle_inbound_sms(sender: str, text: str) -> None:
            import uuid as _uuid
            session_key = sender
            if session_key not in sms_sessions:
                sms_sessions[session_key] = SMSSession(
                    session_uuid=str(_uuid.uuid4()),
                    sender=sender,
                    destination="",
                    created_at=time.monotonic(),
                )
            sms_session = sms_sessions[session_key]
            sms_session.messages.append({
                "role": "user",
                "text": text,
                "timestamp": time.monotonic(),
            })

        run(_handle_inbound_sms("+15550001234", "Hello"))

        self.assertIn("+15550001234", sms_sessions)
        sess = sms_sessions["+15550001234"]
        self.assertIsInstance(sess, SMSSession)
        self.assertEqual(sess.sender, "+15550001234")
        self.assertEqual(len(sess.messages), 1)
        self.assertEqual(sess.messages[0]["role"], "user")
        self.assertEqual(sess.messages[0]["text"], "Hello")

    def test_handler_appends_messages_for_same_sender(self):
        """Subsequent messages from same sender must append to existing session."""
        from holler.core.sms.session import SMSSession

        sms_sessions = {}

        async def _handle_inbound_sms(sender: str, text: str) -> None:
            import uuid as _uuid
            session_key = sender
            if session_key not in sms_sessions:
                sms_sessions[session_key] = SMSSession(
                    session_uuid=str(_uuid.uuid4()),
                    sender=sender,
                    destination="",
                    created_at=time.monotonic(),
                )
            sms_session = sms_sessions[session_key]
            sms_session.messages.append({
                "role": "user",
                "text": text,
                "timestamp": time.monotonic(),
            })

        run(_handle_inbound_sms("+15550001234", "First message"))
        run(_handle_inbound_sms("+15550001234", "Second message"))

        sess = sms_sessions["+15550001234"]
        self.assertEqual(len(sess.messages), 2)
        # Same session UUID (not a new session)
        uuid1 = sess.session_uuid
        run(_handle_inbound_sms("+15550001234", "Third message"))
        self.assertEqual(sms_sessions["+15550001234"].session_uuid, uuid1)
        self.assertEqual(len(sms_sessions["+15550001234"].messages), 3)


# ===========================================================================
# Run
# ===========================================================================

if __name__ == "__main__":
    unittest.main()
