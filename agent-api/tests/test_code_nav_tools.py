"""Tests for code navigation tools."""

from __future__ import annotations

from pathlib import Path

from agent_service.agent.tools.code_nav_tools import (
    run_find_references,
    run_list_symbols,
    run_read_file_range,
    run_search_code,
)


async def test_read_file_range_with_line_numbers(tmp_path: Path):
    (tmp_path / "app.py").write_text("a\nb\nc\nd\n")
    result = await run_read_file_range(
        {"path": "app.py", "start_line": 2, "end_line": 3},
        workspace=tmp_path,
    )
    assert "app.py:2-3" in result
    assert "2:" in result
    assert "3:" in result
    assert "b" in result
    assert "c" in result


async def test_read_file_range_invalid_range(tmp_path: Path):
    (tmp_path / "app.py").write_text("a\n")
    result = await run_read_file_range(
        {"path": "app.py", "start_line": 3, "end_line": 4},
        workspace=tmp_path,
    )
    assert "Error" in result
    assert "out of range" in result


async def test_search_code_plain_text(tmp_path: Path):
    (tmp_path / "a.py").write_text("def hello():\n    return 1\n")
    (tmp_path / "b.py").write_text("def world():\n    return hello()\n")
    result = await run_search_code({"query": "hello"}, workspace=tmp_path)
    assert "Found" in result
    assert "a.py:1:" in result
    assert "b.py:2:" in result


async def test_search_code_regex(tmp_path: Path):
    (tmp_path / "m.py").write_text("foo_1\nfoo_2\nbar\n")
    result = await run_search_code(
        {"query": r"foo_\d", "regex": True},
        workspace=tmp_path,
    )
    assert "m.py:1:" in result
    assert "m.py:2:" in result


async def test_find_references_whole_word(tmp_path: Path):
    (tmp_path / "ref.py").write_text(
        "count = 1\n"
        "counter = 2\n"
        "print(count)\n"
    )
    result = await run_find_references({"symbol": "count"}, workspace=tmp_path)
    assert "ref.py:1:" in result
    assert "ref.py:3:" in result
    assert "counter = 2" not in result


async def test_list_symbols_python(tmp_path: Path):
    (tmp_path / "svc.py").write_text(
        "class Service:\n"
        "    pass\n\n"
        "async def run():\n"
        "    return 1\n"
    )
    result = await run_list_symbols({"path": "svc.py"}, workspace=tmp_path)
    assert "[class] Service" in result
    assert "[function] run" in result


async def test_list_symbols_javascript(tmp_path: Path):
    (tmp_path / "web.js").write_text(
        "class App {}\n"
        "function boot() {}\n"
        "const init = () => {};\n"
    )
    result = await run_list_symbols({"path": "web.js"}, workspace=tmp_path)
    assert "[class] App" in result
    assert "[function] boot" in result
    assert "[function] init" in result


async def test_search_code_skips_binary_files(tmp_path: Path):
    (tmp_path / "code.py").write_text("needle\n")
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01needle\x02")
    result = await run_search_code({"query": "needle"}, workspace=tmp_path)
    assert "code.py:1:" in result
    assert "blob.bin" not in result
