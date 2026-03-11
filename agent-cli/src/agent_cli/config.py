"""User configuration — loads ~/.agent/config.toml and ensures directories."""

from __future__ import annotations

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class CLIConfig:
    """Merged configuration from config file + CLI flags."""

    agent_dir: Path = field(default_factory=lambda: Path.home() / ".openagent")
    model: str | None = None
    preset: str = "coding"
    approval: bool = True
    vi_mode: bool = False

    @property
    def history_file(self) -> Path:
        return self.agent_dir / "history"

    @property
    def conversations_dir(self) -> Path:
        return self.agent_dir / "conversations"


def load_config(path: Path | None = None) -> CLIConfig:
    """Load config from TOML file, falling back to defaults.

    If *path* is None, looks at ``~/.agent/config.toml``.
    Missing file or missing keys are silently ignored.
    """
    cfg = CLIConfig()
    config_path = path or cfg.agent_dir / "config.toml"

    if not config_path.is_file():
        return cfg

    with open(config_path, "rb") as f:
        data = tomllib.load(f)

    if "agent_dir" in data:
        cfg.agent_dir = Path(data["agent_dir"]).expanduser()
    if "model" in data:
        cfg.model = data["model"]
    if "preset" in data:
        cfg.preset = data["preset"]
    if "approval" in data:
        cfg.approval = bool(data["approval"])
    if "vi_mode" in data:
        cfg.vi_mode = bool(data["vi_mode"])

    return cfg


def ensure_dirs(config: CLIConfig) -> None:
    """Create the agent directory structure if it doesn't exist."""
    config.agent_dir.mkdir(parents=True, exist_ok=True)
    config.conversations_dir.mkdir(parents=True, exist_ok=True)
