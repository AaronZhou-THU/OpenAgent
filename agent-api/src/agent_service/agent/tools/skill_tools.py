"""Skill tools — list_skills, read_skill (v4 pattern)."""

from __future__ import annotations

from agent_service.agent.skill_loader import SkillLoader

# ---------------------------------------------------------------------------
# list_skills
# ---------------------------------------------------------------------------

LIST_SKILLS_DEFINITION = {
    "name": "list_skills",
    "description": "List all available skills with their descriptions.",
    "input_schema": {
        "type": "object",
        "properties": {},
    },
}


async def run_list_skills(args: dict, *, skill_loader: SkillLoader) -> str:
    return skill_loader.get_descriptions()


# ---------------------------------------------------------------------------
# read_skill
# ---------------------------------------------------------------------------

READ_SKILL_DEFINITION = {
    "name": "read_skill",
    "description": "Load a skill to gain specialized knowledge for a task. "
    "The skill content will be injected into the conversation.",
    "input_schema": {
        "type": "object",
        "properties": {
            "skill": {
                "type": "string",
                "description": "Name of the skill to load",
            }
        },
        "required": ["skill"],
    },
}


async def run_read_skill(args: dict, *, skill_loader: SkillLoader) -> str:
    name = args["skill"]
    content = skill_loader.get_skill_content(name)
    if content is None:
        available = ", ".join(skill_loader.list_skills()) or "none"
        return f"Error: Unknown skill '{name}'. Available: {available}"

    return (
        f'<skill-loaded name="{name}">\n'
        f"{content}\n"
        f"</skill-loaded>\n\n"
        f"Follow the instructions in the skill above to complete the user's task."
    )
