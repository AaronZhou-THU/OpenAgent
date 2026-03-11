"""Application configuration via pydantic-settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # LLM provider
    llm_provider: str = "anthropic"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_base_url: str | None = None

    # OpenAI
    openai_api_key: str = ""
    openai_base_url: str | None = None

    model: str = "claude-sonnet-4-5-20250929"

    # Agent limits
    max_turns: int = 50
    max_token_budget: int = 200_000
    max_output_tokens: int = 16384

    # Per-role model overrides (empty = use default `model`)
    subagent_model: str = ""  # model for subagents (explore/code/plan/research)
    teammate_model: str = ""  # model for teammate agents
    compact_model: str = ""  # model for context compaction summarization

    # Temperature (0.0–1.0, Anthropic default is 1.0)
    temperature: float = 1.0  # main agent loop
    subagent_temperature: float = 0.5  # subagents — more focused/precise
    teammate_temperature: float = 0.7  # teammates — balanced
    compact_temperature: float = 0.2  # compaction — deterministic summarization

    # Context management
    context_window: int = 200_000  # model's context window size
    compact_threshold: float = 0.7  # compact when input_tokens > this × context_window

    # Paths
    skills_dir: str = "skills"
    prompts_dir: str = "prompts"
    workspace_dir: str = "workspace"

    # Context compaction
    transcript_dir: str = ".transcripts"  # relative to workspace, for audit trail

    # Preset
    default_preset: str = "coding"

    # Bash safety
    bash_timeout: int = 60
    background_timeout: int = 300  # max seconds for background commands
    allowed_commands: list[str] = []  # empty list = allow all

    # Teams
    max_teammates: int = 5  # max concurrent teammate agents

    # Cleanup
    workspace_cleanup_delay: int = 300  # seconds before workspace files are removed

    # LLM retry
    llm_max_retries: int = 3
    llm_retry_base_delay: float = 1.0  # seconds
    llm_retry_max_delay: float = 30.0  # seconds

    # MCP
    mcp_servers_file: str = "mcp_servers.json"

    # Memory
    enable_memory: bool = True

    # Database
    database_url: str = "sqlite+aiosqlite:///./agent.db"

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


@dataclass
class AppState:
    """Shared application state — initialized once in main.py lifespan,
    accessed via ``request.app.state.app_state`` or dependency injection.

    Replaces duplicate module-level globals in routes.py and websocket.py.
    """

    settings: Settings
    client: Any  # LLMClient
    skill_loader: Any  # SkillLoader
    prompt_loader: Any  # PromptLoader
    mcp_manager: Any | None = None
    tool_info: list[dict] = field(default_factory=list)
