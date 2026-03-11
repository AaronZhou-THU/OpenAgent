"""Tests for agent_service.agent.tools.file_tools."""

from __future__ import annotations

from pathlib import Path

import pytest

from agent_service.agent.tools.file_tools import (
    _safe_path,
    run_edit_file,
    run_read_file,
    run_write_file,
)


# ---------------------------------------------------------------------------
# _safe_path tests
# ---------------------------------------------------------------------------


def test_safe_path_valid(tmp_path: Path):
    (tmp_path / "hello.txt").write_text("hi")
    result = _safe_path("hello.txt", tmp_path)
    assert result == (tmp_path / "hello.txt").resolve()


def test_safe_path_traversal_raises(tmp_path: Path):
    with pytest.raises(ValueError, match="escapes workspace"):
        _safe_path("../../etc/passwd", tmp_path)


def test_safe_path_nested(tmp_path: Path):
    sub = tmp_path / "a" / "b"
    sub.mkdir(parents=True)
    (sub / "x.py").write_text("pass")
    result = _safe_path("a/b/x.py", tmp_path)
    assert result == (sub / "x.py").resolve()


# ---------------------------------------------------------------------------
# run_read_file tests
# ---------------------------------------------------------------------------


async def test_read_file(tmp_path: Path):
    (tmp_path / "test.txt").write_text("line1\nline2\nline3\n")
    result = await run_read_file({"path": "test.txt"}, workspace=tmp_path)
    assert "line1" in result
    assert "line2" in result
    assert "line3" in result


async def test_read_file_with_limit(tmp_path: Path):
    content = "\n".join(f"line{i}" for i in range(50))
    (tmp_path / "big.txt").write_text(content)
    result = await run_read_file({"path": "big.txt", "limit": 5}, workspace=tmp_path)
    assert "line0" in result
    assert "line4" in result
    assert "more lines" in result


async def test_read_file_nonexistent(tmp_path: Path):
    result = await run_read_file({"path": "nope.txt"}, workspace=tmp_path)
    assert "Error" in result


# ---------------------------------------------------------------------------
# run_write_file tests
# ---------------------------------------------------------------------------


async def test_write_file_creates(tmp_path: Path):
    result = await run_write_file(
        {"path": "sub/dir/new.py", "content": "x = 1\n"}, workspace=tmp_path
    )
    assert "Wrote" in result
    assert (tmp_path / "sub" / "dir" / "new.py").read_text() == "x = 1\n"


async def test_write_file_overwrites(tmp_path: Path):
    (tmp_path / "exists.txt").write_text("old")
    result = await run_write_file(
        {"path": "exists.txt", "content": "new"}, workspace=tmp_path
    )
    assert "Wrote" in result
    assert (tmp_path / "exists.txt").read_text() == "new"


# ---------------------------------------------------------------------------
# run_edit_file tests
# ---------------------------------------------------------------------------


async def test_edit_file_replaces(tmp_path: Path):
    (tmp_path / "code.py").write_text("def hello():\n    return 'hi'\n")
    result = await run_edit_file(
        {"path": "code.py", "old_text": "return 'hi'", "new_text": "return 'hello'"},
        workspace=tmp_path,
    )
    assert "Edited" in result
    assert "return 'hello'" in (tmp_path / "code.py").read_text()


async def test_edit_file_not_found_text(tmp_path: Path):
    (tmp_path / "code.py").write_text("x = 1")
    result = await run_edit_file(
        {"path": "code.py", "old_text": "NOT HERE", "new_text": "replaced"},
        workspace=tmp_path,
    )
    assert "Error" in result
    assert "not found" in result.lower()


async def test_edit_file_duplicate_text(tmp_path: Path):
    (tmp_path / "code.py").write_text("x = 1\nx = 1\n")
    result = await run_edit_file(
        {"path": "code.py", "old_text": "x = 1", "new_text": "x = 2"},
        workspace=tmp_path,
    )
    assert "Error" in result
    assert "2 times" in result


# ---------------------------------------------------------------------------
# Path traversal security tests (Phase 4.4)
# ---------------------------------------------------------------------------


def test_safe_path_symlink_outside_workspace(tmp_path: Path):
    """Symlink to file outside workspace should be rejected."""
    import tempfile

    # Create an external file
    with tempfile.NamedTemporaryFile(delete=False, suffix=".txt") as f:
        external_file = Path(f.name)
        f.write(b"secret data")

    try:
        # Create a symlink inside workspace pointing outside
        link = tmp_path / "evil_link.txt"
        link.symlink_to(external_file)

        with pytest.raises(ValueError, match="escapes workspace"):
            _safe_path("evil_link.txt", tmp_path)
    finally:
        external_file.unlink(missing_ok=True)


def test_safe_path_intermediate_symlink_outside(tmp_path: Path):
    """Intermediate directory symlink escaping workspace should be rejected."""
    import tempfile

    external_dir = Path(tempfile.mkdtemp())
    (external_dir / "secret.txt").write_text("secret")

    try:
        # Create a symlink dir inside workspace pointing to external dir
        link_dir = tmp_path / "sub"
        link_dir.symlink_to(external_dir)

        with pytest.raises(ValueError, match="escapes workspace"):
            _safe_path("sub/secret.txt", tmp_path)
    finally:
        import shutil
        shutil.rmtree(external_dir, ignore_errors=True)


def test_safe_path_dotdot_traversal(tmp_path: Path):
    """../../../etc/passwd style traversal should be rejected."""
    with pytest.raises(ValueError, match="escapes workspace"):
        _safe_path("../../../etc/passwd", tmp_path)


def test_safe_path_null_byte_injection(tmp_path: Path):
    """Null byte in path should be rejected."""
    with pytest.raises(ValueError, match="null byte"):
        _safe_path("file.txt\x00.jpg", tmp_path)


def test_safe_path_dotdot_in_middle(tmp_path: Path):
    """Path with ../ in the middle escaping workspace should be rejected."""
    (tmp_path / "subdir").mkdir()
    with pytest.raises(ValueError, match="escapes workspace"):
        _safe_path("subdir/../../etc/passwd", tmp_path)


async def test_read_file_traversal_blocked(tmp_path: Path):
    """read_file should block path traversal."""
    result = await run_read_file({"path": "../../etc/passwd"}, workspace=tmp_path)
    assert "Error" in result
    assert "escapes" in result.lower()


async def test_write_file_traversal_blocked(tmp_path: Path):
    """write_file should block path traversal."""
    result = await run_write_file(
        {"path": "../../tmp/evil.txt", "content": "owned"},
        workspace=tmp_path,
    )
    assert "Error" in result
    assert "escapes" in result.lower()
