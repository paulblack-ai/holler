"""Adapter functions for multi-LLM provider support (D-04).

Converts Holler's OpenAI-format tool definitions to provider-specific formats.
Currently supports Anthropic and generic OpenAI-compatible providers.

The core tool definitions in tools.py use OpenAI function calling JSON Schema
format as the canonical representation. Adapters transform this canonical format
to match each provider's expected API shape.

Exports:
    openai_to_anthropic: Convert a single OpenAI tool to Anthropic format.
    openai_tools_to_anthropic: Convert a list of OpenAI tools to Anthropic format.
    anthropic_response_to_tool_calls: Extract tool calls from Anthropic content blocks.
"""
from __future__ import annotations

from typing import List


def openai_to_anthropic(openai_tool: dict) -> dict:
    """Convert a single OpenAI function calling tool to Anthropic tool format.

    Anthropic uses "input_schema" instead of "parameters", and does not accept
    "type" or "strict" keys at the top level of the tool definition.

    Args:
        openai_tool: Tool definition in OpenAI format with keys:
            - type: "function"
            - function: dict with name, description, strict, parameters

    Returns:
        Tool definition in Anthropic format with keys:
            - name: str
            - description: str
            - input_schema: dict (same content as OpenAI "parameters")

    Example:
        openai_tool = {
            "type": "function",
            "function": {"name": "hangup", "description": "...",
                         "strict": True, "parameters": {...}},
        }
        result = openai_to_anthropic(openai_tool)
        # {"name": "hangup", "description": "...", "input_schema": {...}}
    """
    fn = openai_tool["function"]
    return {
        "name": fn["name"],
        "description": fn["description"],
        "input_schema": fn["parameters"],
    }


def openai_tools_to_anthropic(tools: List[dict]) -> List[dict]:
    """Convert a list of OpenAI tools to Anthropic format.

    Args:
        tools: List of tool definitions in OpenAI function calling format.

    Returns:
        List of tool definitions in Anthropic format.
    """
    return [openai_to_anthropic(t) for t in tools]


def anthropic_response_to_tool_calls(content_blocks: list) -> list:
    """Extract tool invocations from an Anthropic API response content block list.

    Anthropic returns content as a list of blocks. Tool invocations have
    type="tool_use". Text blocks are filtered out.

    Args:
        content_blocks: List of Anthropic content blocks from the API response.
            Each block has at minimum a "type" key.
            Tool use blocks additionally have: id, name, input (dict).

    Returns:
        List of tool call dicts with keys:
            - id: str (Anthropic tool use ID)
            - name: str (tool name)
            - arguments: dict (parsed arguments — already a dict, not JSON string)

    Example:
        blocks = [
            {"type": "text", "text": "I will send the SMS."},
            {"type": "tool_use", "id": "toolu_01", "name": "sms",
             "input": {"destination": "+14155551234", "message": "hello"}},
        ]
        result = anthropic_response_to_tool_calls(blocks)
        # [{"id": "toolu_01", "name": "sms",
        #   "arguments": {"destination": "+14155551234", "message": "hello"}}]
    """
    return [
        {
            "id": b["id"],
            "name": b["name"],
            "arguments": b["input"],
        }
        for b in content_blocks
        if b.get("type") == "tool_use"
    ]
