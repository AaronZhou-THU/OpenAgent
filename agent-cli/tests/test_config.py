"""Tests for agent_cli.config — CLIConfig loading and directory creation."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_cli.config import CLIConfig, ensure_dirs, load_config


class TestCLIConfigDefaults:
    """Verify default values of CLIConfig."""

    def test_default_agent_dir(self):
        cfg = CLIConfig()
        assert cfg.agent_dir == Path.home() / ".openagent"

    def test_default_model_is_none(self):
        cfg = CLIConfig()
        assert cfg.model is None

    def test_default_preset(self):
        cfg = CLIConfig()
        assert cfg.preset == "coding"

    def test_default_approval(self):
        cfg = CLIConfig()
        assert cfg.approval is True

    def test_default_vi_mode(self):
        cfg = CLIConfig()
        assert cfg.vi_mode is False

    def test_default_thinking_enabled(self):
        cfg = CLIConfig()
        assert cfg.thinking_enabled is None

    def test_default_thinking_effort(self):
        cfg = CLIConfig()
        assert cfg.thinking_effort is None

    def test_history_file_property(self):
        cfg = CLIConfig()
        assert cfg.history_file == cfg.agent_dir / "history"

    def test_conversations_dir_property(self):
        cfg = CLIConfig()
        assert cfg.conversations_dir == cfg.agent_dir / "conversations"


class TestLoadConfig:
    """Test TOML config loading."""

    def test_missing_file_returns_defaults(self, tmp_path):
        cfg = load_config(tmp_path / "nonexistent.toml")
        assert cfg.preset == "coding"
        assert cfg.model is None

    def test_loads_toml_values(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text(
            'model = "claude-haiku-4-5-20251001"\n'
            'preset = "work"\n'
            "approval = false\n"
            "vi_mode = true\n"
            "thinking_enabled = true\n"
            'thinking_effort = "max"\n'
        )
        cfg = load_config(config_file)
        assert cfg.model == "claude-haiku-4-5-20251001"
        assert cfg.preset == "work"
        assert cfg.approval is False
        assert cfg.vi_mode is True
        assert cfg.thinking_enabled is True
        assert cfg.thinking_effort == "max"

    def test_partial_toml(self, tmp_path):
        config_file = tmp_path / "config.toml"
        config_file.write_text('preset = "debug"\n')
        cfg = load_config(config_file)
        assert cfg.preset == "debug"
        assert cfg.model is None  # not in file, stays default

    def test_agent_dir_override(self, tmp_path):
        config_file = tmp_path / "config.toml"
        custom_dir = tmp_path / "custom_agent"
        config_file.write_text(f'agent_dir = "{custom_dir}"\n')
        cfg = load_config(config_file)
        assert cfg.agent_dir == custom_dir


class TestEnsureDirs:
    """Test directory creation."""

    def test_creates_agent_dir(self, tmp_path):
        cfg = CLIConfig(agent_dir=tmp_path / "new_agent")
        ensure_dirs(cfg)
        assert cfg.agent_dir.is_dir()

    def test_creates_conversations_dir(self, tmp_path):
        cfg = CLIConfig(agent_dir=tmp_path / "new_agent")
        ensure_dirs(cfg)
        assert cfg.conversations_dir.is_dir()

    def test_idempotent(self, tmp_path):
        cfg = CLIConfig(agent_dir=tmp_path / "new_agent")
        ensure_dirs(cfg)
        ensure_dirs(cfg)  # Should not raise
        assert cfg.agent_dir.is_dir()
