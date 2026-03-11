"""Task tool — spawn a subagent with isolated context (v3 pattern)."""

from __future__ import annotations

_READONLY_PARALLEL = (
    " Parallelize: multiple read_file or bash calls for different targets."
    " Do not parallelize when one command depends on another's output."
)

_FULL_PARALLEL = (
    " Parallelize: multiple read_file for different files, multiple"
    " independent bash commands, think alongside anything."
    " Do NOT parallelize: write_file/edit_file to the same file,"
    " or any tool that depends on a previous tool's output."
)

_RESEARCH_PARALLEL = (
    " Parallelize: multiple read_file or bash calls for different targets."
    " Do not parallelize write_file with other tools targeting the same file,"
    " or any tool that depends on a previous tool's output."
)

AGENT_TYPES: dict[str, dict] = {
    "general": {
        "description": "General-purpose agent for multi-step tasks that combine reading, writing, and shell commands",
        "tools": "*",
        "prompt": (
            "You are a general-purpose agent. Handle the task using whatever "
            "tools are appropriate — read files, write files, run commands, "
            "or any combination. Be thorough and return a clear summary."
            + _FULL_PARALLEL
        ),
    },
    "explore": {
        "description": "Read-only agent for exploring code, finding files, searching",
        "tools": ["bash", "read_file", "think"],
        "prompt": (
            "You are an exploration agent. Search and analyze, but never "
            "modify files. Return a concise summary." + _READONLY_PARALLEL
        ),
    },
    "code": {
        "description": "Full agent for implementing features and fixing bugs",
        "tools": "*",
        "prompt": (
            "You are a coding agent. Implement the requested changes "
            "efficiently." + _FULL_PARALLEL
        ),
    },
    "plan": {
        "description": "Planning agent for designing implementation strategies",
        "tools": ["bash", "read_file", "think"],
        "prompt": (
            "You are a planning agent. Analyze the codebase and output a "
            "numbered implementation plan. Do NOT make changes."
            + _READONLY_PARALLEL
        ),
    },
    "research": {
        "description": "Research agent for deep investigation, analysis, and knowledge synthesis",
        "tools": ["bash", "read_file", "write_file", "think"],
        "prompt": (
            "You are a research agent. Investigate the topic thoroughly: "
            "search files, analyze data, synthesize information from multiple "
            "sources. Distinguish facts from inferences — flag uncertainty. "
            "Return a well-structured summary of findings and open questions."
            + _RESEARCH_PARALLEL
        ),
    },
}


def get_agent_descriptions() -> str:
    return "\n".join(
        f"- {name}: {cfg['description']}" for name, cfg in AGENT_TYPES.items()
    )


TASK_DEFINITION = {
    "name": "task",
    "description": (
        "Spawn a subagent for a focused subtask. The subagent runs in "
        "ISOLATED context and returns only a summary.\n\n"
        "You can call multiple task tools in a single response to run "
        "subagents in parallel. Use this for independent subtasks that "
        "don't depend on each other.\n\n"
        f"Agent types:\n{get_agent_descriptions()}"
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Short task name (3-5 words) for progress display",
            },
            "prompt": {
                "type": "string",
                "description": "Detailed instructions for the subagent",
            },
            "agent_type": {
                "type": "string",
                "enum": list(AGENT_TYPES.keys()),
                "description": "Type of agent to spawn",
            },
        },
        "required": ["description", "prompt", "agent_type"],
    },
}
