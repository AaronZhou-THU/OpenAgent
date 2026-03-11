"""Resolve bundled data directories (skills, prompts)."""

from __future__ import annotations

import importlib.resources
from pathlib import Path


def _bundled_data_dir() -> Path:
    return Path(str(importlib.resources.files("agent_service") / "data"))


def get_skills_dir() -> Path:
    return _bundled_data_dir() / "skills"


def get_prompts_dir() -> Path:
    return _bundled_data_dir() / "prompts"
