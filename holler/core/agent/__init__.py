"""Holler agent tool-use protocol package.

Exposes the tool-use layer that bridges LLM function calling to Holler actions.

Exports:
    HOLLER_TOOLS: List of 4 tool definitions in OpenAI function calling format.
    ToolCallSentinel: Dataclass yielded when LLM invokes a tool.
    get_tools: Returns HOLLER_TOOLS.
    ToolExecutor: Dispatches tool calls to Holler subsystems.
    openai_to_anthropic: Convert OpenAI tool format to Anthropic format.
    openai_tools_to_anthropic: Convert a list of OpenAI tools to Anthropic format.
    anthropic_response_to_tool_calls: Extract tool calls from Anthropic response blocks.
"""
from holler.core.agent.tools import HOLLER_TOOLS, ToolCallSentinel, get_tools
from holler.core.agent.executor import ToolExecutor
from holler.core.agent.adapters import (
    openai_to_anthropic,
    openai_tools_to_anthropic,
    anthropic_response_to_tool_calls,
)

__all__ = [
    "HOLLER_TOOLS",
    "ToolCallSentinel",
    "get_tools",
    "ToolExecutor",
    "openai_to_anthropic",
    "openai_tools_to_anthropic",
    "anthropic_response_to_tool_calls",
]
