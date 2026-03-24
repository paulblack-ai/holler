"""OpenAI-compatible streaming LLM client.

Works with any OpenAI-compatible endpoint (D-11): Ollama, OpenAI API,
Anthropic via adapter, or any compatible server. LLM-agnostic from day one.

Agent behavior defined via system message (D-12). Phase 1 uses a simple
conversational responder — tool-use protocol comes in Phase 3.
"""
import asyncio
from dataclasses import dataclass, field
from typing import AsyncGenerator, List, Optional

import structlog

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
    ) -> AsyncGenerator[str, None]:
        """Stream LLM response tokens given a user transcript.

        Args:
            transcript: The user's speech-to-text transcript
            history: Prior conversation turns [{"role": "user"|"assistant", "content": "..."}]

        Yields:
            Individual tokens (str) as they arrive from the LLM
        """
        if self._client is None:
            raise RuntimeError("LLMClient not initialized. Call initialize() first.")

        messages = (
            [{"role": "system", "content": self.config.system_prompt}]
            + (history or [])[-self.config.max_history_turns :]
            + [{"role": "user", "content": transcript}]
        )

        token_count = 0
        try:
            stream = await self._client.chat.completions.create(
                model=self.config.model,
                messages=messages,
                stream=True,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
            )
            async for chunk in stream:
                content = chunk.choices[0].delta.content
                if content is not None:
                    token_count += 1
                    yield content
        except Exception as e:
            logger.error("llm.stream_error", error=str(e))
            raise
        finally:
            logger.info("llm.response_complete", tokens=token_count)

    def build_history_entry(self, role: str, content: str) -> dict:
        """Create a history entry for conversation tracking."""
        return {"role": role, "content": content}
