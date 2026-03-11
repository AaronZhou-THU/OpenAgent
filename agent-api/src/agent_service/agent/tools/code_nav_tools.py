"""Code navigation tools for better repository understanding."""

from __future__ import annotations

import asyncio
import re
from pathlib import Path

from agent_service.agent.tools.file_tools import _safe_path

_MAX_OUTPUT_CHARS = 50_000
_MAX_RESULTS_DEFAULT = 50
_MAX_RESULTS_LIMIT = 200
_MAX_FILE_BYTES = 512 * 1024
_SKIP_DIRS = {
    ".agent",
    ".transcripts",
    ".tasks",
    ".team",
    ".git",
    ".venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
}


READ_FILE_RANGE_DEFINITION = {
    "name": "read_file_range",
    "description": "Read a specific line range from a UTF-8 text file.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to the file"},
            "start_line": {"type": "integer", "description": "1-based start line"},
            "end_line": {"type": "integer", "description": "1-based end line"},
            "include_line_numbers": {
                "type": "boolean",
                "description": "Whether to prefix each line with its line number",
            },
        },
        "required": ["path", "start_line", "end_line"],
    },
}

SEARCH_CODE_DEFINITION = {
    "name": "search_code",
    "description": (
        "Search text across workspace files and return matching file:line snippets."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search text or regex"},
            "path_glob": {
                "type": "string",
                "description": "Optional glob filter, e.g. '**/*.py'",
            },
            "regex": {
                "type": "boolean",
                "description": "Interpret query as regex (default: false)",
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Case-sensitive search (default: false)",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of matches to return (default: 50)",
            },
        },
        "required": ["query"],
    },
}

LIST_SYMBOLS_DEFINITION = {
    "name": "list_symbols",
    "description": "List top-level symbols (functions/classes/types) in a source file.",
    "input_schema": {
        "type": "object",
        "properties": {
            "path": {"type": "string", "description": "Relative path to the file"},
            "max_results": {
                "type": "integer",
                "description": "Maximum number of symbols to return (default: 200)",
            },
        },
        "required": ["path"],
    },
}

FIND_REFERENCES_DEFINITION = {
    "name": "find_references",
    "description": "Find usages of a symbol name across workspace files.",
    "input_schema": {
        "type": "object",
        "properties": {
            "symbol": {"type": "string", "description": "Symbol name to locate"},
            "path_glob": {
                "type": "string",
                "description": "Optional glob filter, e.g. 'src/**/*.ts'",
            },
            "case_sensitive": {
                "type": "boolean",
                "description": "Case-sensitive search (default: true)",
            },
            "whole_word": {
                "type": "boolean",
                "description": "Match whole-word symbol boundaries (default: true)",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of matches to return (default: 50)",
            },
        },
        "required": ["symbol"],
    },
}


def _iter_workspace_files(workspace: Path, path_glob: str) -> list[Path]:
    files: list[Path] = []
    for p in workspace.glob(path_glob):
        if not p.is_file():
            continue
        try:
            rel = p.relative_to(workspace)
        except ValueError:
            continue
        if rel.parts and rel.parts[0] in _SKIP_DIRS:
            continue
        files.append(p)
    files.sort(key=lambda x: str(x))
    return files


def _is_text_file(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            head = f.read(4096)
        if b"\x00" in head:
            return False
        head.decode("utf-8")
        return True
    except Exception:
        return False


def _clamp_results(value: int | None, default: int) -> int:
    if value is None:
        return default
    return max(1, min(int(value), _MAX_RESULTS_LIMIT))


def _build_pattern(query: str, *, regex: bool, case_sensitive: bool) -> re.Pattern[str]:
    if not query.strip():
        raise ValueError("query must not be empty")
    flags = 0 if case_sensitive else re.IGNORECASE
    source = query if regex else re.escape(query)
    return re.compile(source, flags)


async def run_read_file_range(args: dict, *, workspace: Path) -> str:
    try:
        start_line = int(args["start_line"])
        end_line = int(args["end_line"])
        if start_line < 1 or end_line < 1:
            return "Error: start_line and end_line must be >= 1"
        if end_line < start_line:
            return "Error: end_line must be >= start_line"

        fp = _safe_path(args["path"], workspace)
        text = await asyncio.to_thread(fp.read_text)
        lines = text.splitlines()
        total = len(lines)
        if total == 0:
            return f"{args['path']}: file is empty"
        if start_line > total:
            return (
                f"Error: start_line {start_line} out of range for {args['path']} "
                f"(total lines: {total})"
            )

        end_line = min(end_line, total)
        include_numbers = bool(args.get("include_line_numbers", True))

        out: list[str] = [f"{args['path']}:{start_line}-{end_line} (total {total} lines)"]
        for ln in range(start_line, end_line + 1):
            line = lines[ln - 1]
            out.append(f"{ln:>5}: {line}" if include_numbers else line)
        result = "\n".join(out)
        if len(result) > _MAX_OUTPUT_CHARS:
            return result[:_MAX_OUTPUT_CHARS] + "\n... (truncated)"
        return result
    except Exception as e:
        return f"Error: {e}"


def _search_lines(
    *,
    workspace: Path,
    pattern: re.Pattern[str],
    path_glob: str,
    max_results: int,
) -> tuple[list[str], bool]:
    matches: list[str] = []
    truncated = False

    for fp in _iter_workspace_files(workspace, path_glob):
        if fp.stat().st_size > _MAX_FILE_BYTES or not _is_text_file(fp):
            continue
        try:
            text = fp.read_text(encoding="utf-8")
        except Exception:
            continue

        rel = fp.relative_to(workspace)
        for lineno, line in enumerate(text.splitlines(), start=1):
            if not pattern.search(line):
                continue
            snippet = line.strip()
            if len(snippet) > 200:
                snippet = snippet[:200] + "..."
            matches.append(f"{rel}:{lineno}: {snippet}")
            if len(matches) >= max_results:
                truncated = True
                return matches, truncated
    return matches, truncated


async def run_search_code(args: dict, *, workspace: Path) -> str:
    try:
        query = str(args["query"])
        path_glob = str(args.get("path_glob", "**/*"))
        regex = bool(args.get("regex", False))
        case_sensitive = bool(args.get("case_sensitive", False))
        max_results = _clamp_results(args.get("max_results"), _MAX_RESULTS_DEFAULT)

        pattern = _build_pattern(query, regex=regex, case_sensitive=case_sensitive)
        matches, truncated = await asyncio.to_thread(
            _search_lines,
            workspace=workspace,
            pattern=pattern,
            path_glob=path_glob,
            max_results=max_results,
        )
        if not matches:
            return "No matches found."

        header = f"Found {len(matches)} match(es)"
        if truncated:
            header += f" (showing first {len(matches)})"
        return "\n".join([header, *matches])[:_MAX_OUTPUT_CHARS]
    except re.error as e:
        return f"Error: Invalid regex: {e}"
    except Exception as e:
        return f"Error: {e}"


def _symbol_patterns(path: Path) -> list[tuple[str, re.Pattern[str]]]:
    ext = path.suffix.lower()

    if ext == ".py":
        return [
            ("class", re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\b")),
            ("function", re.compile(r"^\s*(?:async\s+def|def)\s+([A-Za-z_][A-Za-z0-9_]*)\b")),
        ]
    if ext in {".js", ".jsx", ".ts", ".tsx"}:
        return [
            ("class", re.compile(r"^\s*class\s+([A-Za-z_$][A-Za-z0-9_$]*)\b")),
            ("function", re.compile(r"^\s*(?:export\s+)?(?:async\s+)?function\s+([A-Za-z_$][A-Za-z0-9_$]*)\b")),
            ("function", re.compile(r"^\s*(?:export\s+)?(?:const|let|var)\s+([A-Za-z_$][A-Za-z0-9_$]*)\s*=\s*(?:async\s*)?\([^)]*\)\s*=>")),
        ]
    if ext == ".go":
        return [
            ("type", re.compile(r"^\s*type\s+([A-Za-z_][A-Za-z0-9_]*)\s+(?:struct|interface)\b")),
            ("function", re.compile(r"^\s*func\s+(?:\([^)]+\)\s*)?([A-Za-z_][A-Za-z0-9_]*)\s*\(")),
        ]
    if ext == ".rs":
        return [
            ("struct", re.compile(r"^\s*(?:pub\s+)?struct\s+([A-Za-z_][A-Za-z0-9_]*)\b")),
            ("enum", re.compile(r"^\s*(?:pub\s+)?enum\s+([A-Za-z_][A-Za-z0-9_]*)\b")),
            ("trait", re.compile(r"^\s*(?:pub\s+)?trait\s+([A-Za-z_][A-Za-z0-9_]*)\b")),
            ("function", re.compile(r"^\s*(?:pub\s+)?fn\s+([A-Za-z_][A-Za-z0-9_]*)\b")),
        ]

    return [
        ("class", re.compile(r"^\s*class\s+([A-Za-z_][A-Za-z0-9_]*)\b")),
        ("function", re.compile(r"^\s*function\s+([A-Za-z_][A-Za-z0-9_]*)\b")),
    ]


async def run_list_symbols(args: dict, *, workspace: Path) -> str:
    try:
        fp = _safe_path(args["path"], workspace)
        if fp.stat().st_size > _MAX_FILE_BYTES:
            return f"Error: File too large for symbol listing ({fp.stat().st_size} bytes)"
        text = await asyncio.to_thread(fp.read_text, encoding="utf-8")
        patterns = _symbol_patterns(fp)
        max_results = _clamp_results(args.get("max_results"), _MAX_RESULTS_LIMIT)

        rel = fp.relative_to(workspace)
        symbols: list[str] = []
        for lineno, line in enumerate(text.splitlines(), start=1):
            for kind, pat in patterns:
                m = pat.search(line)
                if not m:
                    continue
                symbols.append(f"{rel}:{lineno}: [{kind}] {m.group(1)}")
                if len(symbols) >= max_results:
                    break
            if len(symbols) >= max_results:
                break

        if not symbols:
            return f"No symbols found in {args['path']}."
        return "\n".join([f"Symbols in {args['path']}:", *symbols])[:_MAX_OUTPUT_CHARS]
    except Exception as e:
        return f"Error: {e}"


async def run_find_references(args: dict, *, workspace: Path) -> str:
    try:
        symbol = str(args["symbol"])
        if not symbol.strip():
            return "Error: symbol must not be empty"
        case_sensitive = bool(args.get("case_sensitive", True))
        whole_word = bool(args.get("whole_word", True))
        path_glob = str(args.get("path_glob", "**/*"))
        max_results = _clamp_results(args.get("max_results"), _MAX_RESULTS_DEFAULT)

        escaped = re.escape(symbol)
        source = rf"\b{escaped}\b" if whole_word else escaped
        pattern = re.compile(source, 0 if case_sensitive else re.IGNORECASE)

        matches, truncated = await asyncio.to_thread(
            _search_lines,
            workspace=workspace,
            pattern=pattern,
            path_glob=path_glob,
            max_results=max_results,
        )
        if not matches:
            return f"No references found for '{symbol}'."

        header = f"Found {len(matches)} reference(s) for '{symbol}'"
        if truncated:
            header += f" (showing first {len(matches)})"
        return "\n".join([header, *matches])[:_MAX_OUTPUT_CHARS]
    except re.error as e:
        return f"Error: Invalid symbol pattern: {e}"
    except Exception as e:
        return f"Error: {e}"
