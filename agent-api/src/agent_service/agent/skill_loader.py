"""SkillLoader — reads SKILL.md files for on-demand knowledge injection (v4 pattern)."""

from __future__ import annotations

import re
from pathlib import Path


class SkillLoader:
    """
    Scans a skills directory for SKILL.md files.

    Each skill is a folder containing:
    - SKILL.md (required): YAML frontmatter + markdown body
    - scripts/, references/, assets/ (optional)

    Progressive disclosure:
    - Layer 1: name + description (always available, ~100 tokens)
    - Layer 2: Full SKILL.md body (loaded on demand)
    - Layer 3: Resource hints (listed when skill loaded)
    """

    def __init__(self, skills_dir: str | Path) -> None:
        self.skills_dir = Path(skills_dir)
        self.skills: dict[str, dict] = {}
        self.load_skills()

    # ------------------------------------------------------------------

    def load_skills(self) -> None:
        if not self.skills_dir.exists():
            return
        for skill_dir in sorted(self.skills_dir.iterdir()):
            if not skill_dir.is_dir():
                continue
            skill_md = skill_dir / "SKILL.md"
            if not skill_md.exists():
                continue
            skill = self._parse(skill_md)
            if skill:
                self.skills[skill["name"]] = skill

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
            "path": path,
            "dir": path.parent,
        }

    # ------------------------------------------------------------------

    def get_descriptions(self) -> str:
        if not self.skills:
            return "(no skills available)"
        return "\n".join(
            f"- {name}: {s['description']}" for name, s in self.skills.items()
        )

    def get_skill_content(self, name: str) -> str | None:
        if name not in self.skills:
            return None

        skill = self.skills[name]
        content = f"# Skill: {skill['name']}\n\n{skill['body']}"

        resources: list[str] = []
        for folder, label in [
            ("scripts", "Scripts"),
            ("references", "References"),
            ("assets", "Assets"),
        ]:
            folder_path = skill["dir"] / folder
            if folder_path.exists():
                files = list(folder_path.glob("*"))
                if files:
                    resources.append(f"{label}: {', '.join(f.name for f in files)}")

        if resources:
            content += f"\n\n**Available resources in {skill['dir']}:**\n"
            content += "\n".join(f"- {r}" for r in resources)

        return content

    def list_skills(self) -> list[str]:
        return list(self.skills.keys())

    def add_skill(self, name: str, description: str, body: str) -> None:
        """Create a new skill on disk and register it."""
        skill_dir = self.skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        skill_md = skill_dir / "SKILL.md"
        skill_md.write_text(
            f"---\nname: {name}\ndescription: {description}\n---\n\n{body}\n"
        )
        parsed = self._parse(skill_md)
        if parsed:
            self.skills[parsed["name"]] = parsed
