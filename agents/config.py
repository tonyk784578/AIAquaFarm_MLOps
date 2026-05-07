"""Agent configuration — loaded from environment variables."""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class AgentSettings(BaseSettings):
    """Configuration for LangGraph agents."""

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )

    # LLM
    anthropic_api_key: str = Field(..., description="Anthropic API key")
    llm_model: str = "claude-sonnet-4-6"
    llm_temperature: float = 0.0
    llm_max_tokens: int = 4096

    # Services
    backend_url: str = "http://backend:8000"
    redis_url: str = "redis://redis:6379/0"

    # Agent behaviour
    max_agent_iterations: int = 10
    agent_timeout_seconds: int = 120
    log_level: str = "info"


@lru_cache
def get_agent_settings() -> AgentSettings:
    """Return cached agent settings.

    Returns:
        AgentSettings singleton.
    """
    return AgentSettings()
