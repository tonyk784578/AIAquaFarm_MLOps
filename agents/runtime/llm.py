"""Shared async Anthropic client — retry, timeout, structured logging.

Every Claude call from an agent node should go through ``LLMClient`` so
retry policy, model name, and timeouts are applied uniformly.

Usage::

    llm = LLMClient()
    response = await llm.messages(
        system="...", messages=[...], tools=[...],
    )
    decisions = LLMClient.extract_tool_input(response, "decide_control_action")
"""

from __future__ import annotations

from typing import Any

import structlog

from agents.config import get_agent_settings
from agents.runtime.retry import retry_llm

logger = structlog.get_logger()


class LLMUnavailableError(RuntimeError):
    """Raised when the anthropic SDK is not installed at runtime."""


class LLMClient:
    """Thin retry wrapper around ``anthropic.AsyncAnthropic.messages.create``.

    The client is lightweight (no HTTP state): instantiate per-cycle.

    Attributes:
        model: Claude model id.
        max_tokens: Default token limit.
        temperature: Sampling temperature.
        timeout_s: Per-request timeout in seconds.
    """

    def __init__(
        self,
        model: str | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        timeout_s: float = 60.0,
    ) -> None:
        s = get_agent_settings()
        self.api_key = s.anthropic_api_key
        self.model = model or s.llm_model
        self.max_tokens = max_tokens or s.llm_max_tokens
        self.temperature = temperature if temperature is not None else s.llm_temperature
        self.timeout_s = timeout_s

    @retry_llm(max_attempts=4)
    async def messages(
        self,
        system: str,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
    ) -> Any:
        """Call the Anthropic Messages API with retry-on-transient-error.

        Args:
            system: System prompt string.
            messages: Anthropic-format message history.
            tools: Optional tool-use schema list.
            max_tokens: Override default token limit for this call.
            temperature: Override default temperature for this call.

        Returns:
            Anthropic ``Message`` response object.

        Raises:
            LLMUnavailableError: If the ``anthropic`` package is not installed.
        """
        try:
            import anthropic
        except ImportError as exc:
            raise LLMUnavailableError("anthropic SDK is not installed") from exc

        client = anthropic.AsyncAnthropic(api_key=self.api_key, timeout=self.timeout_s)
        kwargs: dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens,
            "temperature": temperature if temperature is not None else self.temperature,
            "system": system,
            "messages": messages,
        }
        if tools:
            kwargs["tools"] = tools

        response = await client.messages.create(**kwargs)
        logger.debug(
            "llm_call",
            model=self.model,
            input_tokens=getattr(response.usage, "input_tokens", None) if hasattr(response, "usage") else None,
            output_tokens=getattr(response.usage, "output_tokens", None) if hasattr(response, "usage") else None,
            stop_reason=getattr(response, "stop_reason", None),
        )
        return response

    # ── Helpers ───────────────────────────────────────────────────────────────

    @staticmethod
    def extract_tool_input(response: Any, tool_name: str) -> dict[str, Any] | None:
        """Return the ``input`` dict of the first matching ``tool_use`` block.

        Args:
            response: Anthropic ``Message`` response.
            tool_name: Tool name to look for.

        Returns:
            The tool input dict, or None if no matching tool_use block exists.
        """
        for block in getattr(response, "content", []) or []:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == tool_name:
                return getattr(block, "input", {}) or {}
        return None

    @staticmethod
    def dump_content(response: Any) -> list[dict[str, Any]]:
        """Serialise response.content into JSON-safe dicts for chat history."""
        out: list[dict[str, Any]] = []
        for block in getattr(response, "content", []) or []:
            if hasattr(block, "model_dump"):
                out.append(block.model_dump())
            else:
                out.append({k: v for k, v in vars(block).items() if not k.startswith("_")})
        return out
