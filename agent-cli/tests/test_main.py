"""Tests for agent_cli.main._build_parser."""

from __future__ import annotations

import importlib.metadata

from agent_cli.main import _build_parser, _get_version


class TestBuildParserDefaults:
    """Verify default values when no flags are passed."""

    def test_default_preset(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.preset == "coding"

    def test_default_workspace(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.workspace is None

    def test_default_model(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.model is None

    def test_default_no_memory(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.no_memory is False

    def test_default_no_approval(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.no_approval is False

    def test_default_max_turns(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.max_turns is None


class TestBuildParserLongFlags:
    """Verify long-form flags set values correctly."""

    def test_preset_long(self):
        parser = _build_parser()
        args = parser.parse_args(["--preset", "work"])
        assert args.preset == "work"

    def test_workspace_long(self):
        parser = _build_parser()
        args = parser.parse_args(["--workspace", "/tmp"])
        assert args.workspace == "/tmp"

    def test_model_long(self):
        parser = _build_parser()
        args = parser.parse_args(["--model", "gpt-4"])
        assert args.model == "gpt-4"

    def test_no_memory_long(self):
        parser = _build_parser()
        args = parser.parse_args(["--no-memory"])
        assert args.no_memory is True

    def test_no_approval_long(self):
        parser = _build_parser()
        args = parser.parse_args(["--no-approval"])
        assert args.no_approval is True

    def test_max_turns_long(self):
        parser = _build_parser()
        args = parser.parse_args(["--max-turns", "10"])
        assert args.max_turns == 10


class TestBuildParserShortFlags:
    """Verify short-form flags (-p, -w, -m) work."""

    def test_preset_short(self):
        parser = _build_parser()
        args = parser.parse_args(["-p", "work"])
        assert args.preset == "work"

    def test_workspace_short(self):
        parser = _build_parser()
        args = parser.parse_args(["-w", "/tmp"])
        assert args.workspace == "/tmp"

    def test_model_short(self):
        parser = _build_parser()
        args = parser.parse_args(["-m", "gpt-4"])
        assert args.model == "gpt-4"


class TestBuildParserCombined:
    """Verify that multiple flags can be combined."""

    def test_all_flags_together(self):
        parser = _build_parser()
        args = parser.parse_args([
            "--preset", "work",
            "--workspace", "/tmp",
            "--model", "gpt-4",
            "--no-memory",
            "--no-approval",
            "--max-turns", "10",
        ])
        assert args.preset == "work"
        assert args.workspace == "/tmp"
        assert args.model == "gpt-4"
        assert args.no_memory is True
        assert args.no_approval is True
        assert args.max_turns == 10

    def test_short_and_long_mixed(self):
        parser = _build_parser()
        args = parser.parse_args(["-p", "debug", "--workspace", "/var", "-m", "o1"])
        assert args.preset == "debug"
        assert args.workspace == "/var"
        assert args.model == "o1"


class TestBuildParserNewFlags:
    """Verify --resume and --version flags."""

    def test_default_resume(self):
        parser = _build_parser()
        args = parser.parse_args([])
        assert args.resume is None

    def test_resume_no_arg_defaults_to_latest(self):
        parser = _build_parser()
        args = parser.parse_args(["--resume"])
        assert args.resume == "latest"

    def test_resume_with_session_id(self):
        parser = _build_parser()
        args = parser.parse_args(["--resume", "abc123"])
        assert args.resume == "abc123"

    def test_resume_combined_with_other_flags(self):
        parser = _build_parser()
        args = parser.parse_args(["--resume", "abc123", "-m", "gpt-4"])
        assert args.resume == "abc123"
        assert args.model == "gpt-4"


class TestGetVersion:
    """Verify package version lookup for the CLI banner."""

    def test_prefers_openagent_app_distribution(self, monkeypatch):
        def fake_version(name: str) -> str:
            if name == "openagent-app":
                return "1.2.3"
            raise importlib.metadata.PackageNotFoundError

        monkeypatch.setattr(importlib.metadata, "version", fake_version)

        assert _get_version() == "openagent 1.2.3"

    def test_falls_back_to_legacy_distribution_name(self, monkeypatch):
        def fake_version(name: str) -> str:
            if name == "openagent":
                return "0.9.0"
            raise importlib.metadata.PackageNotFoundError

        monkeypatch.setattr(importlib.metadata, "version", fake_version)

        assert _get_version() == "openagent 0.9.0"

    def test_uses_static_fallback_when_metadata_is_missing(self, monkeypatch):
        def fake_version(_: str) -> str:
            raise importlib.metadata.PackageNotFoundError

        monkeypatch.setattr(importlib.metadata, "version", fake_version)

        assert _get_version() == "openagent 0.1.0"
