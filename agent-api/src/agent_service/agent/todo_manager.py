"""TodoManager — structured planning with constraints (from v2 pattern)."""

from __future__ import annotations


class TodoManager:
    """
    Per-conversation task list.

    Constraints that enable structured execution:
    - Max 20 items (prevents infinite lists)
    - Only one in_progress at a time (forces focus)
    - Each item needs content, status, activeForm
    """

    def __init__(self) -> None:
        self.items: list[dict] = []

    def update(self, items: list[dict]) -> str:
        validated: list[dict] = []
        in_progress = 0

        for i, item in enumerate(items):
            content = str(item.get("content", "")).strip()
            status = str(item.get("status", "pending")).lower()
            active_form = str(item.get("activeForm", "")).strip()

            if not content or not active_form:
                raise ValueError(f"Item {i}: content and activeForm required")
            if status not in ("pending", "in_progress", "completed"):
                raise ValueError(f"Item {i}: invalid status '{status}'")
            if status == "in_progress":
                in_progress += 1

            validated.append(
                {"content": content, "status": status, "activeForm": active_form}
            )

        if len(validated) > 20:
            raise ValueError("Max 20 todos allowed")
        if in_progress > 1:
            raise ValueError("Only one task can be in_progress at a time")

        self.items = validated
        return self.render()

    def render(self) -> str:
        if not self.items:
            return "No todos."
        lines: list[str] = []
        for t in self.items:
            if t["status"] == "completed":
                lines.append(f"[x] {t['content']}")
            elif t["status"] == "in_progress":
                lines.append(f"[>] {t['content']} <- {t['activeForm']}")
            else:
                lines.append(f"[ ] {t['content']}")
        done = sum(1 for t in self.items if t["status"] == "completed")
        lines.append(f"\n({done}/{len(self.items)} completed)")
        return "\n".join(lines)

    def as_list(self) -> list[dict]:
        return list(self.items)
