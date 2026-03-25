"""Unit tests for SMS package: SMSClient, HollerHook, SMSSession, ComplianceGateway.sms_checked().

All aiosmpplib types are mocked — the library may not be installed.
Tests use asyncio directly (no pytest-asyncio) per project convention.
"""
from __future__ import annotations

import asyncio
import sys
import time
import types
import unittest
from dataclasses import dataclass, field
from typing import Any, Optional
from unittest.mock import AsyncMock, MagicMock, patch


# ---------------------------------------------------------------------------
# Minimal stubs for aiosmpplib so tests work without it installed
# ---------------------------------------------------------------------------

def _make_aiosmpplib_stub():
    """Build a minimal stub module for aiosmpplib."""
    mod = types.ModuleType("aiosmpplib")

    class PhoneNumber:
        def __init__(self, number: str):
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
        def __init__(self):
            self._queue = []

        async def enqueue(self, msg):
            self._queue.append(msg)

    class ESME:
        def __init__(self, *args, **kwargs):
            self.broker = Broker()
            self._started = False

        async def start(self):
            self._started = True

        async def stop(self):
            self._started = False

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


# Inject stub before importing holler.core.sms so TYPE_CHECKING paths work
_aiosmpplib_stub = _make_aiosmpplib_stub()
sys.modules["aiosmpplib"] = _aiosmpplib_stub


# ---------------------------------------------------------------------------
# Now import the modules under test
# ---------------------------------------------------------------------------

from holler.core.sms.session import SMSSession  # noqa: E402
from holler.core.sms.hook import HollerHook  # noqa: E402
from holler.core.sms.client import SMSClient, SMSConfig  # noqa: E402


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def run(coro):
    """Run coroutine synchronously (no pytest-asyncio on system Python)."""
    return asyncio.get_event_loop().run_until_complete(coro)


# ===========================================================================
# SMSConfig tests
# ===========================================================================

class TestSMSConfig(unittest.TestCase):
    def test_defaults(self):
        cfg = SMSConfig()
        self.assertEqual(cfg.smsc_host, "127.0.0.1")
        self.assertEqual(cfg.smsc_port, 2775)
        self.assertEqual(cfg.system_id, "holler")
        self.assertEqual(cfg.password, "")
        self.assertEqual(cfg.source_address, "")

    def test_custom_values(self):
        cfg = SMSConfig(smsc_host="10.0.0.1", smsc_port=2776, system_id="myid",
                        password="secret", source_address="+15550001234")
        self.assertEqual(cfg.smsc_host, "10.0.0.1")
        self.assertEqual(cfg.smsc_port, 2776)
        self.assertEqual(cfg.system_id, "myid")
        self.assertEqual(cfg.password, "secret")
        self.assertEqual(cfg.source_address, "+15550001234")


# ===========================================================================
# SMSClient tests
# ===========================================================================

class TestSMSClientInit(unittest.TestCase):
    def test_init_creates_empty_delivery_store(self):
        client = SMSClient()
        self.assertIsInstance(client._delivery_store, dict)
        self.assertEqual(len(client._delivery_store), 0)

    def test_init_esme_and_task_are_none(self):
        client = SMSClient()
        self.assertIsNone(client._esme)
        self.assertIsNone(client._task)

    def test_get_status_returns_unknown_for_untracked(self):
        client = SMSClient()
        self.assertEqual(client.get_status("nonexistent-id"), "unknown")


class TestSMSClientSend(unittest.TestCase):
    def test_send_sets_status_to_queued(self):
        """After send(), get_status() returns 'queued'."""
        client = SMSClient(SMSConfig(source_address="+15550001234"))
        # Mock _esme.broker.enqueue
        mock_esme = MagicMock()
        mock_esme.broker.enqueue = AsyncMock()
        client._esme = mock_esme

        run(client.send("+15550005678", "Hello", log_id="msg-001"))

        self.assertEqual(client.get_status("msg-001"), "queued")

    def test_send_calls_enqueue(self):
        """send() calls _esme.broker.enqueue() with a message."""
        client = SMSClient(SMSConfig(source_address="+15550001234"))
        mock_esme = MagicMock()
        mock_esme.broker.enqueue = AsyncMock()
        client._esme = mock_esme

        run(client.send("+15550005678", "Test message", log_id="msg-002"))

        mock_esme.broker.enqueue.assert_called_once()


# ===========================================================================
# HollerHook tests
# ===========================================================================

class TestHollerHookDeliveryReceipt(unittest.TestCase):
    def _make_receipt_deliver_sm(self, stat: str, log_id: str):
        """Create a DeliverSm stub that is_receipt() and has a stat to parse."""
        ds = _aiosmpplib_stub.DeliverSm(
            short_message=f"id:{log_id} sub:001 dlvrd:001 submit date:2601010000 done date:2601010000 stat:{stat} err:000 text:Hello",
            source=_aiosmpplib_stub.PhoneNumber("+15550001234"),
            log_id=log_id,
            receipt=True,
        )
        return ds

    def _make_inbound_deliver_sm(self, sender: str, text: str):
        """Create a DeliverSm that is NOT a receipt (regular inbound SMS)."""
        ds = _aiosmpplib_stub.DeliverSm(
            short_message=text,
            source=_aiosmpplib_stub.PhoneNumber(sender),
            log_id=None,
            receipt=False,
        )
        return ds

    def test_receipt_delivrd_maps_to_delivered(self):
        store = {}
        hook = HollerHook(store)
        msg = self._make_receipt_deliver_sm("DELIVRD", "msg-001")
        run(hook.received(msg, pdu=None, client_id="test"))
        self.assertEqual(store.get("msg-001"), "delivered")

    def test_receipt_undeliv_maps_to_failed(self):
        store = {}
        hook = HollerHook(store)
        msg = self._make_receipt_deliver_sm("UNDELIV", "msg-002")
        run(hook.received(msg, pdu=None, client_id="test"))
        self.assertEqual(store.get("msg-002"), "failed")

    def test_receipt_rejectd_maps_to_failed(self):
        store = {}
        hook = HollerHook(store)
        msg = self._make_receipt_deliver_sm("REJECTD", "msg-003")
        run(hook.received(msg, pdu=None, client_id="test"))
        self.assertEqual(store.get("msg-003"), "failed")

    def test_receipt_expired_maps_to_expired(self):
        store = {}
        hook = HollerHook(store)
        msg = self._make_receipt_deliver_sm("EXPIRED", "msg-004")
        run(hook.received(msg, pdu=None, client_id="test"))
        self.assertEqual(store.get("msg-004"), "expired")

    def test_receipt_acceptd_maps_to_accepted(self):
        store = {}
        hook = HollerHook(store)
        msg = self._make_receipt_deliver_sm("ACCEPTD", "msg-005")
        run(hook.received(msg, pdu=None, client_id="test"))
        self.assertEqual(store.get("msg-005"), "accepted")

    def test_inbound_sms_calls_handler(self):
        """Non-receipt DeliverSm triggers inbound_handler(sender, text)."""
        store = {}
        received_calls = []

        async def handler(sender, text):
            received_calls.append((sender, text))

        hook = HollerHook(store, inbound_handler=handler)
        msg = self._make_inbound_deliver_sm("+15559990000", "Hello from user")
        run(hook.received(msg, pdu=None, client_id="test"))

        self.assertEqual(len(received_calls), 1)
        self.assertEqual(received_calls[0][0], "+15559990000")
        self.assertEqual(received_calls[0][1], "Hello from user")

    def test_inbound_sms_no_handler_no_error(self):
        """Non-receipt DeliverSm with no handler set does not raise."""
        store = {}
        hook = HollerHook(store, inbound_handler=None)
        msg = self._make_inbound_deliver_sm("+15559990000", "Hello")
        # Should not raise
        run(hook.received(msg, pdu=None, client_id="test"))

    def test_receipt_does_not_call_inbound_handler(self):
        """Delivery receipt must not call inbound_handler."""
        store = {}
        handler = AsyncMock()
        hook = HollerHook(store, inbound_handler=handler)
        msg = self._make_receipt_deliver_sm("DELIVRD", "msg-006")
        run(hook.received(msg, pdu=None, client_id="test"))
        handler.assert_not_called()


# ===========================================================================
# SMSSession tests
# ===========================================================================

class TestSMSSession(unittest.TestCase):
    def test_session_has_required_fields(self):
        sess = SMSSession(
            session_uuid="uuid-1",
            sender="+15550001234",
            destination="+15550005678",
            created_at=time.monotonic(),
        )
        self.assertEqual(sess.session_uuid, "uuid-1")
        self.assertEqual(sess.sender, "+15550001234")
        self.assertEqual(sess.destination, "+15550005678")
        self.assertIsInstance(sess.messages, list)
        self.assertEqual(len(sess.messages), 0)

    def test_messages_default_is_empty_list(self):
        s1 = SMSSession("a", "+1111", "+2222", created_at=0.0)
        s2 = SMSSession("b", "+3333", "+4444", created_at=0.0)
        s1.messages.append({"role": "user", "text": "hi", "timestamp": 0.0})
        # s2.messages should be independent
        self.assertEqual(len(s2.messages), 0)

    def test_created_at_is_float(self):
        t = time.monotonic()
        sess = SMSSession("x", "+1", "+2", created_at=t)
        self.assertIsInstance(sess.created_at, float)


# ===========================================================================
# ComplianceGateway.sms_checked() tests (Task 2 — added here)
# ===========================================================================

class TestSMSChecked(unittest.TestCase):
    """Tests for ComplianceGateway.sms_checked()."""

    def _make_session(self, destination="+15550001234"):
        from holler.core.compliance.gateway import ComplianceResult
        # Minimal TelecomSession-like object (use a simple namespace)
        session = MagicMock()
        session.session_uuid = "sess-001"
        session.call_uuid = "call-001"
        session.did = "+15550009999"
        session.destination = destination
        session.jurisdiction = "us"
        session.compliance_result = None
        return session

    def _make_gateway(self, module_result, timeout=2.0):
        """Return a ComplianceGateway with a mocked router and audit log."""
        from holler.core.compliance.gateway import ComplianceGateway, ComplianceResult

        router = MagicMock()
        if isinstance(module_result, Exception):
            router.resolve.side_effect = module_result
        else:
            module = MagicMock()
            module.check_outbound = AsyncMock(return_value=module_result)
            router.resolve.return_value = module

        audit = MagicMock()
        audit.write = AsyncMock()

        gw = ComplianceGateway(router=router, audit_log=audit, timeout=timeout)
        return gw

    def test_passing_compliance_calls_send_and_returns_log_id(self):
        """sms_checked() with passing result calls sms_client.send() and returns log_id."""
        from holler.core.compliance.gateway import ComplianceResult

        result = ComplianceResult(passed=True, reason="ok", check_type="us_sms")
        gw = self._make_gateway(result)
        session = self._make_session()

        sms_client = MagicMock()
        sms_client.send = AsyncMock()

        pool = MagicMock()
        pool.release = AsyncMock()

        log_id = run(gw.sms_checked(sms_client, pool, session, "Hello", "msg-100"))

        self.assertEqual(log_id, "msg-100")
        sms_client.send.assert_called_once_with(session.destination, "Hello", "msg-100")
        pool.release.assert_not_called()

    def test_blocking_compliance_raises_and_releases_did(self):
        """sms_checked() with DNC match raises ComplianceBlockError and releases DID."""
        from holler.core.compliance.gateway import ComplianceResult, ComplianceBlockError

        result = ComplianceResult(passed=False, reason="dnc_match", check_type="dnc")
        gw = self._make_gateway(result)
        session = self._make_session()

        sms_client = MagicMock()
        sms_client.send = AsyncMock()

        pool = MagicMock()
        pool.release = AsyncMock()

        with self.assertRaises(ComplianceBlockError):
            run(gw.sms_checked(sms_client, pool, session, "Hello", "msg-101"))

        pool.release.assert_called_once_with(session.did)
        sms_client.send.assert_not_called()

    def test_always_writes_audit_log_with_channel_sms(self):
        """sms_checked() always writes audit log with channel='sms'."""
        from holler.core.compliance.gateway import ComplianceResult

        result = ComplianceResult(passed=True, reason="ok", check_type="us_sms")
        gw = self._make_gateway(result)
        session = self._make_session()

        sms_client = MagicMock()
        sms_client.send = AsyncMock()
        pool = MagicMock()
        pool.release = AsyncMock()

        run(gw.sms_checked(sms_client, pool, session, "Hello", "msg-102"))

        gw._audit.write.assert_called_once()
        call_kwargs = gw._audit.write.call_args[0][0]
        self.assertEqual(call_kwargs.get("channel"), "sms")

    def test_timeout_raises_compliance_block_error(self):
        """sms_checked() with compliance timeout raises ComplianceBlockError (fail-closed)."""
        from holler.core.compliance.gateway import ComplianceResult, ComplianceBlockError

        # Use very short timeout and a slow check_outbound
        async def slow_check(dest, session):
            await asyncio.sleep(5)  # Exceeds timeout
            return ComplianceResult(passed=True, reason="ok", check_type="timeout_test")

        router = MagicMock()
        module = MagicMock()
        module.check_outbound = slow_check
        router.resolve.return_value = module

        audit = MagicMock()
        audit.write = AsyncMock()

        from holler.core.compliance.gateway import ComplianceGateway
        gw = ComplianceGateway(router=router, audit_log=audit, timeout=0.01)

        session = self._make_session()
        sms_client = MagicMock()
        sms_client.send = AsyncMock()
        pool = MagicMock()
        pool.release = AsyncMock()

        with self.assertRaises(ComplianceBlockError):
            run(gw.sms_checked(sms_client, pool, session, "Hello", "msg-103"))

        # Audit should have been written
        gw._audit.write.assert_called_once()
        # DID should be released
        pool.release.assert_called_once_with(session.did)


# ===========================================================================
# Run
# ===========================================================================

if __name__ == "__main__":
    unittest.main()
