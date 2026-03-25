"""Tool definitions for the Holler agent tool-use protocol.

Defines the four Holler actions as OpenAI function calling JSON Schema tools
(D-01). All tools use strict mode with additionalProperties=False. Optional
parameters follow the nullable type pattern required by strict mode Pitfall 4.

Exports:
    HOLLER_TOOLS: List of 4 tool definitions in OpenAI function calling format.
    ToolCallSentinel: Dataclass yielded when LLM invokes a tool instead of text.
    get_tools(): Helper returning HOLLER_TOOLS.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


# ---------------------------------------------------------------------------
# Tool definitions — OpenAI function calling JSON Schema format (D-01)
# ---------------------------------------------------------------------------

HOLLER_TOOLS: List[dict] = [
    {
        "type": "function",
        "function": {
            "name": "call",
            "description": (
                "Place an outbound phone call to a number. "
                "Returns call UUID and session info."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {
                        "type": "string",
                        "description": "E.164 phone number e.g. +14155551234",
                    },
                    "prompt": {
                        "type": ["string", "null"],
                        "description": (
                            "Optional system prompt for the call agent. "
                            "Pass null to use the default prompt."
                        ),
                    },
                },
                "required": ["destination", "prompt"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sms",
            "description": "Send an SMS message. Returns message ID and delivery status.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "destination": {
                        "type": "string",
                        "description": "E.164 destination phone number e.g. +14155551234",
                    },
                    "message": {
                        "type": "string",
                        "description": "SMS text body (max 160 chars for single segment)",
                    },
                },
                "required": ["destination", "message"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "hangup",
            "description": "Terminate an active call. Returns confirmation.",
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "call_uuid": {
                        "type": "string",
                        "description": "UUID of the active call to terminate",
                    },
                },
                "required": ["call_uuid"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "transfer",
            "description": (
                "Blind transfer an active call to a new destination. "
                "Destination must pass compliance checks."
            ),
            "strict": True,
            "parameters": {
                "type": "object",
                "properties": {
                    "call_uuid": {
                        "type": "string",
                        "description": "UUID of the active call to transfer",
                    },
                    "destination": {
                        "type": "string",
                        "description": "E.164 destination for transfer e.g. +15550001234",
                    },
                },
                "required": ["call_uuid", "destination"],
                "additionalProperties": False,
            },
        },
    },
]


def get_tools() -> List[dict]:
    """Return the list of Holler tool definitions.

    Returns:
        HOLLER_TOOLS — four tool definitions in OpenAI function calling format.
    """
    return HOLLER_TOOLS


# ---------------------------------------------------------------------------
# ToolCallSentinel
# ---------------------------------------------------------------------------

@dataclass
class ToolCallSentinel:
    """Sentinel yielded by LLMClient.stream_response() when the LLM invokes a tool.

    The pipeline coordinator intercepts this sentinel and routes tool calls
    through ToolExecutor instead of streaming text to TTS.

    Attributes:
        tool_calls: List of tool invocations from the LLM response.
            Each entry has: {"id": str, "name": str, "arguments": str (JSON)}
    """
    tool_calls: list = field(default_factory=list)
