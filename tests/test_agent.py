"""Tests for the agent tool-use protocol layer.

Tests cover:
- HOLLER_TOOLS: 4 tool definitions in OpenAI function calling format
- ToolCallSentinel: dataclass holding tool_calls list
- get_tools(): returns HOLLER_TOOLS
- ToolExecutor: dispatches tool calls to Holler actions
- Adapter functions: openai_to_anthropic, anthropic_response_to_tool_calls
"""
import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from holler.core.agent.tools import HOLLER_TOOLS, ToolCallSentinel, get_tools
from holler.core.agent.executor import ToolExecutor
from holler.core.agent.adapters import openai_to_anthropic, anthropic_response_to_tool_calls, openai_tools_to_anthropic
from holler.core.compliance.gateway import ComplianceBlockError
from holler.core.telecom.session import TelecomSession


# ---------------------------------------------------------------------------
# HOLLER_TOOLS structure tests
# ---------------------------------------------------------------------------

def test_holler_tools_is_list_of_four():
    assert isinstance(HOLLER_TOOLS, list)
    assert len(HOLLER_TOOLS) == 4


def test_all_tools_have_type_function():
    for tool in HOLLER_TOOLS:
        assert tool["type"] == "function", f"Tool missing type=function: {tool}"


def test_all_tools_have_strict_true():
    for tool in HOLLER_TOOLS:
        fn = tool["function"]
        assert fn.get("strict") is True, f"Tool {fn.get('name')} missing strict=True"


def test_all_tools_have_additional_properties_false():
    for tool in HOLLER_TOOLS:
        fn = tool["function"]
        params = fn["parameters"]
        assert params.get("additionalProperties") is False, (
            f"Tool {fn.get('name')} missing additionalProperties=False"
        )


def test_tool_names_are_correct():
    names = {tool["function"]["name"] for tool in HOLLER_TOOLS}
    assert names == {"call", "sms", "hangup", "transfer"}


# ---------------------------------------------------------------------------
# call tool schema
# ---------------------------------------------------------------------------

def _get_tool(name):
    for tool in HOLLER_TOOLS:
        if tool["function"]["name"] == name:
            return tool
    raise KeyError(f"Tool {name!r} not found")


def test_call_tool_required_fields():
    tool = _get_tool("call")
    fn = tool["function"]
    required = fn["parameters"]["required"]
    # destination and prompt are required (prompt is nullable, required per strict mode Pitfall 4)
    assert "destination" in required
    assert "prompt" in required


def test_call_tool_destination_type_string():
    tool = _get_tool("call")
    props = tool["function"]["parameters"]["properties"]
    assert props["destination"]["type"] == "string"


def test_call_tool_prompt_is_nullable():
    """Prompt must use nullable type pattern for strict mode (Pitfall 4)."""
    tool = _get_tool("call")
    props = tool["function"]["parameters"]["properties"]
    prompt_type = props["prompt"]["type"]
    # Must be list ["string", "null"] for nullable in strict mode
    assert isinstance(prompt_type, list)
    assert "string" in prompt_type
    assert "null" in prompt_type


# ---------------------------------------------------------------------------
# sms tool schema
# ---------------------------------------------------------------------------

def test_sms_tool_required_fields():
    tool = _get_tool("sms")
    fn = tool["function"]
    required = fn["parameters"]["required"]
    assert "destination" in required
    assert "message" in required


def test_sms_tool_both_string_type():
    tool = _get_tool("sms")
    props = tool["function"]["parameters"]["properties"]
    assert props["destination"]["type"] == "string"
    assert props["message"]["type"] == "string"


# ---------------------------------------------------------------------------
# hangup tool schema
# ---------------------------------------------------------------------------

def test_hangup_tool_required_fields():
    tool = _get_tool("hangup")
    fn = tool["function"]
    required = fn["parameters"]["required"]
    assert "call_uuid" in required


def test_hangup_tool_call_uuid_type():
    tool = _get_tool("hangup")
    props = tool["function"]["parameters"]["properties"]
    assert props["call_uuid"]["type"] == "string"


# ---------------------------------------------------------------------------
# transfer tool schema
# ---------------------------------------------------------------------------

def test_transfer_tool_required_fields():
    tool = _get_tool("transfer")
    fn = tool["function"]
    required = fn["parameters"]["required"]
    assert "call_uuid" in required
    assert "destination" in required


def test_transfer_tool_both_string_type():
    tool = _get_tool("transfer")
    props = tool["function"]["parameters"]["properties"]
    assert props["call_uuid"]["type"] == "string"
    assert props["destination"]["type"] == "string"


# ---------------------------------------------------------------------------
# get_tools() helper
# ---------------------------------------------------------------------------

def test_get_tools_returns_holler_tools():
    result = get_tools()
    assert result is HOLLER_TOOLS


# ---------------------------------------------------------------------------
# ToolCallSentinel dataclass
# ---------------------------------------------------------------------------

def test_tool_call_sentinel_holds_tool_calls():
    calls = [{"id": "tc_1", "name": "hangup", "arguments": '{"call_uuid": "abc"}'}]
    sentinel = ToolCallSentinel(tool_calls=calls)
    assert sentinel.tool_calls == calls


def test_tool_call_sentinel_is_dataclass():
    from dataclasses import fields
    f = fields(ToolCallSentinel)
    field_names = {field.name for field in f}
    assert "tool_calls" in field_names


# ---------------------------------------------------------------------------
# ToolExecutor tests
# ---------------------------------------------------------------------------

def _make_session(did="+15550001234", jurisdiction="us"):
    """Create a minimal TelecomSession for testing."""
    return TelecomSession(
        session_uuid="sess-001",
        call_uuid="call-001",
        did=did,
        destination="+14155551234",
        jurisdiction=jurisdiction,
    )


def _make_executor():
    """Create ToolExecutor with all mocked dependencies."""
    esl = MagicMock()
    esl.hangup = AsyncMock()
    esl.send_raw = AsyncMock(return_value="+OK")
    sms_client = MagicMock()
    gateway = MagicMock()
    gateway.originate_checked = AsyncMock(return_value="call-uuid-999")
    gateway.sms_checked = AsyncMock(return_value=None)
    gateway._router = MagicMock()
    pool = MagicMock()
    pool.checkout = AsyncMock(return_value="+15559999999")
    pool.release = AsyncMock()
    executor = ToolExecutor(esl=esl, sms_client=sms_client, compliance_gateway=gateway, pool=pool)
    return executor, esl, sms_client, gateway, pool


# --- hangup ---

def test_execute_hangup_calls_esl_hangup():
    executor, esl, _, _, _ = _make_executor()
    session = _make_session()
    result = asyncio.get_event_loop().run_until_complete(
        executor.execute("hangup", {"call_uuid": "abc"}, session)
    )
    esl.hangup.assert_called_once_with("abc")
    assert result == {"status": "ok"}


# --- sms ---

def test_execute_sms_calls_gateway_sms_checked():
    executor, _, sms_client, gateway, pool = _make_executor()
    session = _make_session()
    result = asyncio.get_event_loop().run_until_complete(
        executor.execute("sms", {"destination": "+14155551234", "message": "hi"}, session)
    )
    assert gateway.sms_checked.called
    assert result["status"] == "ok"
    assert "message_id" in result


def test_execute_sms_returns_message_id():
    executor, _, _, gateway, _ = _make_executor()
    session = _make_session()
    result = asyncio.get_event_loop().run_until_complete(
        executor.execute("sms", {"destination": "+14155551234", "message": "hello"}, session)
    )
    assert isinstance(result.get("message_id"), str)
    assert len(result["message_id"]) > 0


def test_execute_sms_constructs_valid_telecom_session():
    """Verify _execute_sms() passes a fully-constructed TelecomSession to gateway.sms_checked()."""
    executor, _, sms_client, gateway, pool = _make_executor()
    session = _make_session(did="+15550001234", jurisdiction="us")

    asyncio.get_event_loop().run_until_complete(
        executor.execute("sms", {"destination": "+14155551234", "message": "hello"}, session)
    )

    assert gateway.sms_checked.called
    call_args = gateway.sms_checked.call_args
    # Third positional arg is the TelecomSession
    session_arg = call_args[0][2]  # (sms_client, pool, session_for_sms, message, log_id)
    assert isinstance(session_arg, TelecomSession)
    # session_uuid must be a non-empty string
    assert isinstance(session_arg.session_uuid, str)
    assert len(session_arg.session_uuid) > 0
    # call_uuid must be empty string (SMS has no call)
    assert session_arg.call_uuid == ""
    # did must match parent session
    assert session_arg.did == session.did
    # destination must match SMS destination argument
    assert session_arg.destination == "+14155551234"
    # jurisdiction must match parent session
    assert session_arg.jurisdiction == session.jurisdiction


# --- call ---

def test_execute_call_calls_gateway_originate_checked():
    executor, esl, _, gateway, _ = _make_executor()
    session = _make_session()
    result = asyncio.get_event_loop().run_until_complete(
        executor.execute("call", {"destination": "+14155551234", "prompt": None}, session)
    )
    assert gateway.originate_checked.called
    assert result["status"] == "ok"
    assert "call_uuid" in result


# --- transfer ---

def test_execute_transfer_sends_uuid_transfer_command():
    executor, esl, _, gateway, _ = _make_executor()
    session = _make_session()
    # Mock the compliance module check
    mock_module = MagicMock()
    mock_result = MagicMock()
    mock_result.passed = True
    mock_module.check_outbound = AsyncMock(return_value=mock_result)
    gateway._router.resolve = MagicMock(return_value=mock_module)

    result = asyncio.get_event_loop().run_until_complete(
        executor.execute("transfer", {"call_uuid": "call-001", "destination": "+15559876543"}, session)
    )

    assert esl.send_raw.called
    raw_cmd = esl.send_raw.call_args[0][0]
    assert "uuid_transfer" in raw_cmd
    assert result["status"] == "ok"
    assert result["transferred_to"] == "+15559876543"


def test_execute_transfer_blocked_by_compliance():
    executor, esl, _, gateway, _ = _make_executor()
    session = _make_session()
    # Compliance module denies the transfer
    mock_module = MagicMock()
    mock_result = MagicMock()
    mock_result.passed = False
    mock_result.reason = "DNC match"
    mock_module.check_outbound = AsyncMock(return_value=mock_result)
    gateway._router.resolve = MagicMock(return_value=mock_module)

    result = asyncio.get_event_loop().run_until_complete(
        executor.execute("transfer", {"call_uuid": "call-001", "destination": "+15559876543"}, session)
    )

    assert result["status"] == "blocked"
    assert "reason" in result
    # ESL send_raw must NOT be called when transfer is blocked
    esl.send_raw.assert_not_called()


# --- unknown tool ---

def test_execute_unknown_tool_returns_error():
    executor, _, _, _, _ = _make_executor()
    session = _make_session()
    result = asyncio.get_event_loop().run_until_complete(
        executor.execute("unknown_tool", {}, session)
    )
    assert result["status"] == "error"
    assert "unknown_tool" in result["reason"]


# --- compliance block handling (D-02) ---

def test_execute_sms_compliance_block_returns_blocked_dict():
    executor, _, _, gateway, _ = _make_executor()
    gateway.sms_checked = AsyncMock(side_effect=ComplianceBlockError("DNC list match"))
    session = _make_session()
    result = asyncio.get_event_loop().run_until_complete(
        executor.execute("sms", {"destination": "+14155551234", "message": "hi"}, session)
    )
    assert result["status"] == "blocked"
    assert "DNC list match" in result["reason"]


def test_execute_call_compliance_block_returns_blocked_dict():
    executor, _, _, gateway, _ = _make_executor()
    gateway.originate_checked = AsyncMock(side_effect=ComplianceBlockError("TCPA violation"))
    session = _make_session()
    result = asyncio.get_event_loop().run_until_complete(
        executor.execute("call", {"destination": "+14155551234", "prompt": None}, session)
    )
    assert result["status"] == "blocked"
    assert "TCPA violation" in result["reason"]


# ---------------------------------------------------------------------------
# Adapter tests
# ---------------------------------------------------------------------------

def test_openai_to_anthropic_converts_parameters_to_input_schema():
    openai_tool = {
        "type": "function",
        "function": {
            "name": "sms",
            "description": "Send an SMS message.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {"type": "string"},
                    "message": {"type": "string"},
                },
                "required": ["destination", "message"],
                "additionalProperties": False,
            },
        },
    }
    result = openai_to_anthropic(openai_tool)
    assert result["name"] == "sms"
    assert result["description"] == "Send an SMS message."
    assert "input_schema" in result
    # Must NOT contain "type" or "strict" at top level
    assert "type" not in result
    assert "strict" not in result


def test_openai_to_anthropic_input_schema_matches_parameters():
    openai_tool = {
        "type": "function",
        "function": {
            "name": "hangup",
            "description": "Terminate a call.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {"call_uuid": {"type": "string"}},
                "required": ["call_uuid"],
                "additionalProperties": False,
            },
        },
    }
    result = openai_to_anthropic(openai_tool)
    assert result["input_schema"] == openai_tool["function"]["parameters"]


def test_anthropic_response_to_tool_calls_extracts_tool_use_blocks():
    content_blocks = [
        {"type": "text", "text": "I will send the SMS."},
        {
            "type": "tool_use",
            "id": "toolu_01",
            "name": "sms",
            "input": {"destination": "+14155551234", "message": "hello"},
        },
    ]
    result = anthropic_response_to_tool_calls(content_blocks)
    assert len(result) == 1
    assert result[0]["id"] == "toolu_01"
    assert result[0]["name"] == "sms"
    assert result[0]["arguments"] == {"destination": "+14155551234", "message": "hello"}


def test_anthropic_response_to_tool_calls_filters_non_tool_use():
    content_blocks = [
        {"type": "text", "text": "Just text, no tool use."},
    ]
    result = anthropic_response_to_tool_calls(content_blocks)
    assert result == []


def test_anthropic_response_to_tool_calls_multiple_tools():
    content_blocks = [
        {"type": "tool_use", "id": "tc_1", "name": "call", "input": {"destination": "+1555", "prompt": None}},
        {"type": "tool_use", "id": "tc_2", "name": "sms", "input": {"destination": "+1444", "message": "hi"}},
    ]
    result = anthropic_response_to_tool_calls(content_blocks)
    assert len(result) == 2
    assert result[0]["name"] == "call"
    assert result[1]["name"] == "sms"


def test_openai_tools_to_anthropic_converts_all():
    result = openai_tools_to_anthropic(HOLLER_TOOLS)
    assert len(result) == 4
    for anthropic_tool in result:
        assert "input_schema" in anthropic_tool
        assert "name" in anthropic_tool
        assert "description" in anthropic_tool
        assert "type" not in anthropic_tool
        assert "strict" not in anthropic_tool
