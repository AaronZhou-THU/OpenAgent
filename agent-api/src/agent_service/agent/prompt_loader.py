"""PromptLoader — reads PROMPT.md preset files for system prompt injection."""

from __future__ import annotations

import re
from pathlib import Path


class PromptLoader:
    """
    Scans a prompts directory for PROMPT.md preset files.

    Each preset is a folder containing:
    - PROMPT.md (required): YAML frontmatter + markdown body

    The body supports {workspace} placeholder substitution at runtime.
    """

    def __init__(self, prompts_dir: str | Path) -> None:
        self.prompts_dir = Path(prompts_dir)
        self.prompts: dict[str, dict] = {}
        self.load_prompts()

    def load_prompts(self) -> None:
        if not self.prompts_dir.exists():
            return
        for prompt_dir in sorted(self.prompts_dir.iterdir()):
            if not prompt_dir.is_dir():
                continue
            prompt_md = prompt_dir / "PROMPT.md"
            if not prompt_md.exists():
                continue
            prompt = self._parse(prompt_md)
            if prompt:
                self.prompts[prompt["name"]] = prompt

    def _parse(self, path: Path) -> dict | None:
        content = path.read_text()
        match = re.match(r"^---\s*\n(.*?)\n---\s*\n(.*)$", content, re.DOTALL)
        if not match:
            return None

        frontmatter, body = match.groups()
        meta: dict[str, str] = {}
        for line in frontmatter.strip().splitlines():
            if ":" in line:
                key, value = line.split(":", 1)
                meta[key.strip()] = value.strip().strip("\"'")

        if "name" not in meta or "description" not in meta:
            return None

        return {
            "name": meta["name"],
            "description": meta["description"],
            "body": body.strip(),
        }

    def get_body(self, name: str) -> str | None:
        """Return the preset body text, or None if not found."""
        if name not in self.prompts:
            return None
        return self.prompts[name]["body"]

    def list_presets(self) -> list[dict]:
        """Return [{name, description}] for all loaded presets."""
        return [
            {"name": p["name"], "description": p["description"]}
            for p in self.prompts.values()
        ]
