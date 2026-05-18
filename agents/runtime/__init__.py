"""Agent runtime layer — cross-cutting concerns for reliable agent execution.

Modules
-------
    retry        — tenacity decorators for LLM + HTTP calls
    http         — shared async HTTP client (X-Service-Key, timeouts, retry)
    llm          — shared async Anthropic client (timeout, retry)
    state_store  — Redis-backed cycle/optimization state + bounded history
    event_bus    — Redis pub/sub for live agent events (SSE source)
    auth         — X-Service-Key FastAPI dependency
"""

from agents.runtime.auth import require_service_key
from agents.runtime.event_bus import AgentEvent, EventBus
from agents.runtime.http import AgentHTTPClient
from agents.runtime.llm import LLMClient, LLMUnavailableError
from agents.runtime.retry import retry_http, retry_llm
from agents.runtime.state_store import StateStore

__all__ = [
    "AgentEvent",
    "AgentHTTPClient",
    "EventBus",
    "LLMClient",
    "LLMUnavailableError",
    "StateStore",
    "require_service_key",
    "retry_http",
    "retry_llm",
]
