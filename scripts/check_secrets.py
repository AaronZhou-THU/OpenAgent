#!/usr/bin/env python3
"""Lightweight secret scanner for tracked or staged repository files.

Usage:
  python scripts/check_secrets.py            # scan tracked files
  python scripts/check_secrets.py path ...   # scan specific files
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ALLOWLIST = ROOT / ".secretsignore"

IGNORE_PARTS = {
    ".git",
    ".venv",
    "node_modules",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    "__pycache__",
    "dist",
    "build",
}

BLOCKED_FILENAMES = {
    ".env",
    ".env.local",
    ".env.production",
    ".env.development",
    ".env.test",
    "id_rsa",
    "id_ed25519",
}

BLOCKED_SUFFIXES = {".pem", ".key", ".p12", ".pfx"}

PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Anthropic API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{16,}\b")),
    ("OpenAI project key", re.compile(r"\bsk-proj-[A-Za-z0-9_-]{16,}\b")),
    ("GitHub personal access token", re.compile(r"\bghp_[A-Za-z0-9]{20,}\b")),
    ("GitHub fine-grained token", re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}\b")),
    ("AWS access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("Google API key", re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b")),
    ("Slack token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("Private key block", re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |)?PRIVATE KEY-----")),
]


def load_allowlist() -> dict[str, set[str]]:
    allowed: dict[str, set[str]] = {}
    if not ALLOWLIST.exists():
        return allowed
    for raw_line in ALLOWLIST.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        path, _, snippet = line.partition("\t")
        if not path or not snippet:
            raise SystemExit(f"Invalid allowlist entry in {ALLOWLIST}: {raw_line!r}")
        allowed.setdefault(path, set()).add(snippet)
    return allowed


def tracked_files() -> list[Path]:
    result = subprocess.run(
        ["git", "-C", str(ROOT), "ls-files"],
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def is_ignored(path: Path) -> bool:
    return any(part in IGNORE_PARTS for part in path.parts)


def is_binary(path: Path) -> bool:
    try:
        return b"\x00" in path.read_bytes()[:4096]
    except OSError:
        return True


def should_skip(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    return is_ignored(rel) or not path.is_file() or is_binary(path)


def scan_file(path: Path, allowed: dict[str, set[str]]) -> list[str]:
    rel = path.relative_to(ROOT).as_posix()
    findings: list[str] = []

    if path.name in BLOCKED_FILENAMES or path.suffix in BLOCKED_SUFFIXES:
        findings.append(f"{rel}: tracked secret-bearing filename")
        return findings

    try:
        text = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return findings

    allowed_snippets = allowed.get(rel, set())
    for lineno, line in enumerate(text.splitlines(), start=1):
        if any(snippet in line for snippet in allowed_snippets):
            continue
        for name, pattern in PATTERNS:
            match = pattern.search(line)
            if match:
                findings.append(f"{rel}:{lineno}: {name}: {match.group(0)}")
    return findings


def main(argv: list[str]) -> int:
    allowed = load_allowlist()
    paths = [Path(arg).resolve() for arg in argv] if argv else tracked_files()
    findings: list[str] = []

    for path in paths:
        if not str(path).startswith(str(ROOT)):
            continue
        if should_skip(path):
            continue
        findings.extend(scan_file(path, allowed))

    if findings:
        print("Potential secrets detected:\n", file=sys.stderr)
        for finding in findings:
            print(f"  - {finding}", file=sys.stderr)
        print(
            "\nIf a match is an intentional documentation example, add an allowlist entry to .secretsignore.",
            file=sys.stderr,
        )
        return 1

    print("No secrets detected.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
