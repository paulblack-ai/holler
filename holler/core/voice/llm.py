"""OpenAI-compatible streaming LLM client.

Works with any OpenAI-compatible endpoint (D-11): Ollama, OpenAI API,
Anthropic via adapter, or any compatible server. LLM-agnostic from day one.

Agent behavior defined via system message (D-12). Phase 1 uses a simple
conversational responder — tool-use protocol comes in Phase 3.
"""
import asyncio
import json
from dataclasses import dataclass, field
from typing import AsyncGenerator, List, Optional, Union

import structlog

from holler.core.agent.tools import ToolCallSentinel

logger = structlog.get_logger()

DEFAULT_SYSTEM_PROMPT = (
    "You are a helpful voice assistant. Keep your responses concise and natural "
    "for spoken conversation. Respond in 1-3 sentences unless the user asks for "
    "more detail. Do not use markdown, bullet points, or formatting — speak naturally."
)


@dataclass
class LLMConfig:
    base_url: str = "http://localhost:11434/v1"   # Ollama default
    api_key: str = "ollama"                        # Placeholder for local models
    model: str = "llama3.2"
    system_prompt: str = DEFAULT_SYSTEM_PROMPT
    max_tokens: int = 150                          # Short for voice responses
    temperature: float = 0.7
    max_history_turns: int = 10                    # Keep last N turns in context


class LLMClient:
    """Streaming LLM client using OpenAI-compatible API."""

    def __init__(self, config: Optional[LLMConfig] = None):
        self.config = config or LLMConfig()
        self._client = None

    async def initialize(self) -> None:
        """Create the async OpenAI client. Call once at startup."""
        from openai import AsyncOpenAI
        self._client = AsyncOpenAI(
            base_url=self.config.base_url,
            api_key=self.config.api_key,
        )
        logger.info("llm.initialized", base_url=self.config.base_url, model=self.config.model)

    async def stream_response(
        self,
        transcript: str,
        history: Optional[List[dict]] = None,
        tools: Optional[List[dict]] = None,
    ) -> AsyncGenerator[Union[str, ToolCallSentinel], None]:
        """Stream LLM response tokens given a user transcript.

        When tools are provided and the LLM invokes a tool instead of speaking,
        a ToolCallSentinel is yielded as the last item. The pipeline coordinator
        intercepts it and routes execution through ToolExecutor.

        When no tools are provided (or LLM responds with text), only str tokens
        are yielded — fully backward compatible.

        Args:
            transcript: The user's speech-to-text transcript.
            history: Prior conversation turns [{"role": "user"|"assistant", "content": "..."}].
            tools: Optional list of tool definitions in OpenAI function calling format.
                   When provided, enables tool-calling mode. Pass None for text-only mode.

        Yields:
            str tokens as they arrive, or a single ToolCallSentinel if the LLM
            invokes a tool instead of generating text.
        """
        if self._client is None:
            raise RuntimeError("LLMClient not initialized. Call initialize() first.")

        messages = (
            [{"role": "system", "content": self.config.system_prompt}]
            + (history or [])[-self.config.max_history_turns :]
            + [{"role": "user", "content": transcript}]
        )

        token_count = 0
        tool_calls_accumulator: dict = {}  # index -> {"id": str, "name": str, "arguments": str}

        try:
            create_kwargs = dict(
                model=self.config.model,
                messages=messages,
                stream=True,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
            if tools:
                create_kwargs["tools"] = tools
                create_kwargs["tool_choice"] = "auto"

            stream = await self._client.chat.completions.create(**create_kwargs)

            async for chunk in stream:
                delta = chunk.choices[0].delta

                # Text token path
                if delta.content is not None:
                    token_count += 1
                    yield delta.content

                # Tool-call accumulation path
                if hasattr(delta, "tool_calls") and delta.tool_calls:
                    for tc in delta.tool_calls:
                        idx = tc.index
                        if idx not in tool_calls_accumulator:
                            tool_calls_accumulator[idx] = {
                                "id": tc.id or "",
                                "name": tc.function.name or "" if tc.function else "",
                                "arguments": "",
                            }
                        if tc.id:
                            tool_calls_accumulator[idx]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_accumulator[idx]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_accumulator[idx]["arguments"] += tc.function.arguments

            # Yield sentinel if any tool calls were accumulated
            if tool_calls_accumulator:
                yield ToolCallSentinel(list(tool_calls_accumulator.values()))

        except Exception as e:
            logger.error("llm.stream_error", error=str(e))
            raise
        finally:
            logger.info("llm.response_complete", tokens=token_count)

    def build_tool_result_entry(self, tool_call_id: str, result: dict) -> dict:
        """Create a tool result message for conversation history.

        Args:
            tool_call_id: The tool call ID from the LLM's tool invocation.
            result: The dict result returned by ToolExecutor.execute().

        Returns:
            History entry in OpenAI tool result format:
            {"role": "tool", "tool_call_id": str, "content": str (JSON)}
        """
        return {
            "role": "tool",
            "tool_call_id": tool_call_id,
            "content": json.dumps(result),
        }

    def build_history_entry(self, role: str, content: str) -> dict:
        """Create a history entry for conversation tracking."""
        return {"role": role, "content": content}
