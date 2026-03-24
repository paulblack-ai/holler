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
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch, call

from holler.core.freeswitch.esl import FreeSwitchESL, ESLConfig


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
    @pytest.mark.asyncio
    async def test_connect_success_when_status_contains_UP(self):
        """connect() should succeed when FreeSWITCH status contains 'UP'."""
        mock_client = AsyncMock()
        mock_client.send = AsyncMock(return_value=FakeESLResponse("FreeSWITCH is UP"))

        with patch("holler.core.freeswitch.esl.FreeSwitchESL._make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            await esl.connect()
            mock_client.connect.assert_awaited_once()
            mock_client.send.assert_awaited_once_with("api status")

    @pytest.mark.asyncio
    async def test_connect_raises_when_status_missing_UP(self):
        """connect() should raise RuntimeError if FreeSWITCH is not UP."""
        mock_client = AsyncMock()
        mock_client.send = AsyncMock(return_value=FakeESLResponse("FreeSWITCH is DOWN"))

        with patch("holler.core.freeswitch.esl.FreeSwitchESL._make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            with pytest.raises(RuntimeError, match="FreeSWITCH not ready"):
                await esl.connect()

    @pytest.mark.asyncio
    async def test_connect_raises_when_status_is_error(self):
        """connect() should raise RuntimeError on empty/error status."""
        mock_client = AsyncMock()
        mock_client.send = AsyncMock(return_value=FakeESLResponse("-ERR connection refused"))

        with patch("holler.core.freeswitch.esl.FreeSwitchESL._make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            with pytest.raises(RuntimeError, match="FreeSWITCH not ready"):
                await esl.connect()


class TestFreeSwitchESLOriginate:
    @pytest.mark.asyncio
    async def test_originate_returns_call_uuid_on_ok(self):
        """originate() should parse and return the UUID from '+OK <uuid>'."""
        mock_client = AsyncMock()
        status_resp = FakeESLResponse("FreeSWITCH is UP")
        originate_resp = FakeESLResponse("+OK abc-123-uuid")
        mock_client.send = AsyncMock(side_effect=[status_resp, originate_resp])

        with patch("holler.core.freeswitch.esl.FreeSwitchESL._make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            await esl.connect()
            call_uuid = await esl.originate("+14155551234", "session-xyz")
            assert call_uuid == "abc-123-uuid"

    @pytest.mark.asyncio
    async def test_originate_raises_on_err(self):
        """originate() should raise RuntimeError on '-ERR' response."""
        mock_client = AsyncMock()
        status_resp = FakeESLResponse("FreeSWITCH is UP")
        originate_resp = FakeESLResponse("-ERR CHANNEL_UNACCEPTABLE")
        mock_client.send = AsyncMock(side_effect=[status_resp, originate_resp])

        with patch("holler.core.freeswitch.esl.FreeSwitchESL._make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            await esl.connect()
            with pytest.raises(RuntimeError, match="Originate failed"):
                await esl.originate("+14155551234", "session-xyz")

    @pytest.mark.asyncio
    async def test_originate_sends_correct_command(self):
        """originate() should send the correct ESL originate command."""
        mock_client = AsyncMock()
        status_resp = FakeESLResponse("FreeSWITCH is UP")
        originate_resp = FakeESLResponse("+OK call-uuid-999")
        mock_client.send = AsyncMock(side_effect=[status_resp, originate_resp])

        with patch("holler.core.freeswitch.esl.FreeSwitchESL._make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            await esl.connect()
            await esl.originate("+14155551234", "sess-001", gateway="sip_trunk")

            # Check that the originate command was sent (second call after status)
            originate_call = mock_client.send.call_args_list[1]
            cmd = originate_call[0][0]
            assert "api originate" in cmd
            assert "session_uuid=sess-001" in cmd
            assert "sofia/gateway/sip_trunk/+14155551234" in cmd
            assert "&park()" in cmd


class TestFreeSwitchESLHangup:
    @pytest.mark.asyncio
    async def test_hangup_sends_uuid_kill_command(self):
        """hangup() should send 'api uuid_kill <call_uuid>'."""
        mock_client = AsyncMock()
        status_resp = FakeESLResponse("FreeSWITCH is UP")
        hangup_resp = FakeESLResponse("+OK")
        mock_client.send = AsyncMock(side_effect=[status_resp, hangup_resp])

        with patch("holler.core.freeswitch.esl.FreeSwitchESL._make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            await esl.connect()
            await esl.hangup("call-uuid-999")

            hangup_call = mock_client.send.call_args_list[1]
            cmd = hangup_call[0][0]
            assert "api uuid_kill" in cmd
            assert "call-uuid-999" in cmd

    @pytest.mark.asyncio
    async def test_hangup_uses_normal_clearing_by_default(self):
        """hangup() default cause is NORMAL_CLEARING."""
        mock_client = AsyncMock()
        status_resp = FakeESLResponse("FreeSWITCH is UP")
        hangup_resp = FakeESLResponse("+OK")
        mock_client.send = AsyncMock(side_effect=[status_resp, hangup_resp])

        with patch("holler.core.freeswitch.esl.FreeSwitchESL._make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            await esl.connect()
            await esl.hangup("call-uuid-999")

            hangup_call = mock_client.send.call_args_list[1]
            cmd = hangup_call[0][0]
            assert "NORMAL_CLEARING" in cmd


class TestFreeSwitchESLAudioStream:
    @pytest.mark.asyncio
    async def test_start_audio_stream_sends_correct_command(self):
        """start_audio_stream() should send 'api uuid_audio_stream <uuid> start <ws_url> mono 16k'."""
        mock_client = AsyncMock()
        status_resp = FakeESLResponse("FreeSWITCH is UP")
        stream_resp = FakeESLResponse("+OK")
        mock_client.send = AsyncMock(side_effect=[status_resp, stream_resp])

        with patch("holler.core.freeswitch.esl.FreeSwitchESL._make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            await esl.connect()
            await esl.start_audio_stream("call-uuid-001", "ws://127.0.0.1:8765/voice/call-uuid-001")

            stream_call = mock_client.send.call_args_list[1]
            cmd = stream_call[0][0]
            assert "api uuid_audio_stream" in cmd
            assert "call-uuid-001" in cmd
            assert "start" in cmd
            assert "ws://127.0.0.1:8765/voice/call-uuid-001" in cmd
            assert "mono" in cmd
            assert "16k" in cmd

    @pytest.mark.asyncio
    async def test_stop_audio_stream_sends_correct_command(self):
        """stop_audio_stream() should send 'api uuid_audio_stream <uuid> stop'."""
        mock_client = AsyncMock()
        status_resp = FakeESLResponse("FreeSWITCH is UP")
        stop_resp = FakeESLResponse("+OK")
        mock_client.send = AsyncMock(side_effect=[status_resp, stop_resp])

        with patch("holler.core.freeswitch.esl.FreeSwitchESL._make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            await esl.connect()
            await esl.stop_audio_stream("call-uuid-001")

            stop_call = mock_client.send.call_args_list[1]
            cmd = stop_call[0][0]
            assert "api uuid_audio_stream" in cmd
            assert "call-uuid-001" in cmd
            assert "stop" in cmd


class TestFreeSwitchESLContextManager:
    @pytest.mark.asyncio
    async def test_async_context_manager_connects_and_disconnects(self):
        """async with FreeSwitchESL() should connect on entry and disconnect on exit."""
        mock_client = AsyncMock()
        status_resp = FakeESLResponse("FreeSWITCH is UP")
        mock_client.send = AsyncMock(return_value=status_resp)

        with patch("holler.core.freeswitch.esl.FreeSwitchESL._make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            async with esl as ctx:
                assert ctx is esl
                mock_client.connect.assert_awaited_once()

            # After exit, close should be called
            mock_client.close.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_async_context_manager_disconnects_on_exception(self):
        """Context manager should call disconnect even if an exception occurs."""
        mock_client = AsyncMock()
        status_resp = FakeESLResponse("FreeSWITCH is UP")
        mock_client.send = AsyncMock(return_value=status_resp)

        with patch("holler.core.freeswitch.esl.FreeSwitchESL._make_inbound", return_value=mock_client):
            esl = FreeSwitchESL()
            try:
                async with esl:
                    raise ValueError("Test error")
            except ValueError:
                pass

            mock_client.close.assert_awaited_once()
