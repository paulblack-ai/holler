"""Unit tests for FreeSWITCH ESL client wrapper.

Tests use mocked Genesis Inbound to verify:
- connect() verifies "UP" in status response
- connect() raises RuntimeError when status missing "UP"
- originate() parses "+OK uuid-value" and returns UUID
- originate() raises RuntimeError on "-ERR reason"
- hangup() sends correct uuid_kill command
- start_audio_stream() sends correct uuid_audio_stream command
- async context manager calls connect/disconnect
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from holler.core.freeswitch.esl import FreeSwitchESL, ESLConfig


def run(coro):
    """Helper: run a coroutine synchronously in tests."""
    return asyncio.get_event_loop().run_until_complete(coro)


class FakeESLResponse:
    """Simulates a Genesis ESL response object."""

    def __init__(self, body: str):
        self._body = body

    def __str__(self):
        return self._body


class TestESLConfig:
    def test_default_host(self):
        config = ESLConfig()
        assert config.host == "127.0.0.1"

    def test_default_port(self):
        config = ESLConfig()
        assert config.port == 8021

    def test_default_password(self):
        config = ESLConfig()
        assert config.password == "ClueCon"

    def test_default_audio_stream_ws_base(self):
        config = ESLConfig()
        assert config.audio_stream_ws_base == "ws://127.0.0.1:8765/voice"

    def test_custom_config(self):
        config = ESLConfig(host="192.168.1.1", port=9021, password="secret")
        assert config.host == "192.168.1.1"
        assert config.port == 9021
        assert config.password == "secret"


class TestFreeSwitchESLConnect:
    def test_connect_success_when_status_contains_UP(self):
        """connect() should succeed when FreeSWITCH status contains 'UP'."""
        mock_client = AsyncMock()
        mock_client.send = AsyncMock(return_value=FakeESLResponse("FreeSWITCH is UP"))

        with patch.object(FreeSwitchESL, "_make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            run(esl.connect())
            mock_client.connect.assert_awaited_once()
            mock_client.send.assert_awaited_once_with("api status")

    def test_connect_raises_when_status_missing_UP(self):
        """connect() should raise RuntimeError if FreeSWITCH is not UP."""
        mock_client = AsyncMock()
        mock_client.send = AsyncMock(return_value=FakeESLResponse("FreeSWITCH is DOWN"))

        with patch.object(FreeSwitchESL, "_make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            with pytest.raises(RuntimeError, match="FreeSWITCH not ready"):
                run(esl.connect())

    def test_connect_raises_when_status_is_error(self):
        """connect() should raise RuntimeError on empty/error status."""
        mock_client = AsyncMock()
        mock_client.send = AsyncMock(return_value=FakeESLResponse("-ERR connection refused"))

        with patch.object(FreeSwitchESL, "_make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            with pytest.raises(RuntimeError, match="FreeSWITCH not ready"):
                run(esl.connect())


class TestFreeSwitchESLOriginate:
    def _make_esl_connected(self, responses):
        """Build a connected ESL with canned send() responses."""
        mock_client = AsyncMock()
        mock_client.send = AsyncMock(side_effect=responses)
        return mock_client

    def test_originate_returns_call_uuid_on_ok(self):
        """originate() should parse and return the UUID from '+OK <uuid>'."""
        mock_client = self._make_esl_connected([
            FakeESLResponse("FreeSWITCH is UP"),
            FakeESLResponse("+OK abc-123-uuid"),
        ])

        with patch.object(FreeSwitchESL, "_make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            run(esl.connect())
            call_uuid = run(esl.originate("+14155551234", "session-xyz"))
            assert call_uuid == "abc-123-uuid"

    def test_originate_raises_on_err(self):
        """originate() should raise RuntimeError on '-ERR' response."""
        mock_client = self._make_esl_connected([
            FakeESLResponse("FreeSWITCH is UP"),
            FakeESLResponse("-ERR CHANNEL_UNACCEPTABLE"),
        ])

        with patch.object(FreeSwitchESL, "_make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            run(esl.connect())
            with pytest.raises(RuntimeError, match="Originate failed"):
                run(esl.originate("+14155551234", "session-xyz"))

    def test_originate_sends_correct_command(self):
        """originate() should send the correct ESL originate command."""
        mock_client = self._make_esl_connected([
            FakeESLResponse("FreeSWITCH is UP"),
            FakeESLResponse("+OK call-uuid-999"),
        ])

        with patch.object(FreeSwitchESL, "_make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            run(esl.connect())
            run(esl.originate("+14155551234", "sess-001", gateway="sip_trunk"))

            # Check that the originate command was sent (second call after status)
            originate_call = mock_client.send.call_args_list[1]
            cmd = originate_call[0][0]
            assert "api originate" in cmd
            assert "session_uuid=sess-001" in cmd
            assert "sofia/gateway/sip_trunk/+14155551234" in cmd
            assert "&park()" in cmd


class TestFreeSwitchESLHangup:
    def test_hangup_sends_uuid_kill_command(self):
        """hangup() should send 'api uuid_kill <call_uuid>'."""
        mock_client = AsyncMock()
        mock_client.send = AsyncMock(side_effect=[
            FakeESLResponse("FreeSWITCH is UP"),
            FakeESLResponse("+OK"),
        ])

        with patch.object(FreeSwitchESL, "_make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            run(esl.connect())
            run(esl.hangup("call-uuid-999"))

            hangup_call = mock_client.send.call_args_list[1]
            cmd = hangup_call[0][0]
            assert "api uuid_kill" in cmd
            assert "call-uuid-999" in cmd

    def test_hangup_uses_normal_clearing_by_default(self):
        """hangup() default cause is NORMAL_CLEARING."""
        mock_client = AsyncMock()
        mock_client.send = AsyncMock(side_effect=[
            FakeESLResponse("FreeSWITCH is UP"),
            FakeESLResponse("+OK"),
        ])

        with patch.object(FreeSwitchESL, "_make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            run(esl.connect())
            run(esl.hangup("call-uuid-999"))

            hangup_call = mock_client.send.call_args_list[1]
            cmd = hangup_call[0][0]
            assert "NORMAL_CLEARING" in cmd


class TestFreeSwitchESLAudioStream:
    def test_start_audio_stream_sends_correct_command(self):
        """start_audio_stream() should send 'api uuid_audio_stream <uuid> start <ws_url> mono 16k'."""
        mock_client = AsyncMock()
        mock_client.send = AsyncMock(side_effect=[
            FakeESLResponse("FreeSWITCH is UP"),
            FakeESLResponse("+OK"),
        ])

        with patch.object(FreeSwitchESL, "_make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            run(esl.connect())
            run(esl.start_audio_stream("call-uuid-001", "ws://127.0.0.1:8765/voice/call-uuid-001"))

            stream_call = mock_client.send.call_args_list[1]
            cmd = stream_call[0][0]
            assert "api uuid_audio_stream" in cmd
            assert "call-uuid-001" in cmd
            assert "start" in cmd
            assert "ws://127.0.0.1:8765/voice/call-uuid-001" in cmd
            assert "mono" in cmd
            assert "16k" in cmd

    def test_stop_audio_stream_sends_correct_command(self):
        """stop_audio_stream() should send 'api uuid_audio_stream <uuid> stop'."""
        mock_client = AsyncMock()
        mock_client.send = AsyncMock(side_effect=[
            FakeESLResponse("FreeSWITCH is UP"),
            FakeESLResponse("+OK"),
        ])

        with patch.object(FreeSwitchESL, "_make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            run(esl.connect())
            run(esl.stop_audio_stream("call-uuid-001"))

            stop_call = mock_client.send.call_args_list[1]
            cmd = stop_call[0][0]
            assert "api uuid_audio_stream" in cmd
            assert "call-uuid-001" in cmd
            assert "stop" in cmd


class TestFreeSwitchESLContextManager:
    def test_async_context_manager_connects_and_disconnects(self):
        """async with FreeSwitchESL() should connect on entry and disconnect on exit."""
        mock_client = AsyncMock()
        mock_client.send = AsyncMock(return_value=FakeESLResponse("FreeSWITCH is UP"))

        async def _run():
            async with FreeSwitchESL() as esl:
                mock_client.connect.assert_awaited_once()
                return esl

        with patch.object(FreeSwitchESL, "_make_inbound", return_value=mock_client):
            run(_run())
            mock_client.close.assert_awaited_once()

    def test_async_context_manager_disconnects_on_exception(self):
        """Context manager should call disconnect even if an exception occurs."""
        mock_client = AsyncMock()
        mock_client.send = AsyncMock(return_value=FakeESLResponse("FreeSWITCH is UP"))

        async def _run():
            try:
                async with FreeSwitchESL():
                    raise ValueError("Test error")
            except ValueError:
                pass

        with patch.object(FreeSwitchESL, "_make_inbound", return_value=mock_client):
            run(_run())
            mock_client.close.assert_awaited_once()
