"""Unit tests for the pure code-path jail predicate (Issue #12 T2)."""
from __future__ import annotations

from pathlib import Path

from src.domain.code_path_guard import (
    is_team_memory_path,
    is_within_code_root,
    resolve_write_target,
    validate_write_target,
)


def test_within_code_root_accepts_nested_file(tmp_path: Path):
    root = tmp_path / "code"
    root.mkdir()
    (root / "sub").mkdir()
    target = root / "sub" / "train.py"
    target.write_text("x")
    assert is_within_code_root(target, root) is True


def test_outside_code_root_rejected(tmp_path: Path):
    root = tmp_path / "code"
    root.mkdir()
    outside = tmp_path / "outside.py"
    outside.write_text("x")
    assert is_within_code_root(outside, root) is False


def test_symlink_target_rejected(tmp_path: Path):
    root = tmp_path / "code"
    root.mkdir()
    real = tmp_path / "real.py"
    real.write_text("x")
    link = root / "link.py"
    link.symlink_to(real)
    assert is_within_code_root(link, root) is False


def test_dotdot_escape_rejected(tmp_path: Path):
    root = tmp_path / "code"
    root.mkdir()
    target = root / ".." / "escape.py"
    assert is_within_code_root(target, root) is False


def test_team_memory_namespace_detected(tmp_path: Path):
    assert is_team_memory_path(tmp_path / "runs" / "r1" / "manifest.json", tmp_path) is True
    assert is_team_memory_path(tmp_path / "code-revisions" / "x", tmp_path) is True
    assert is_team_memory_path(tmp_path / "datasets" / "d1", tmp_path) is True
    assert is_team_memory_path(tmp_path / ".mlagent-local" / "f.lock", tmp_path) is True
    assert is_team_memory_path(tmp_path / "code" / "train.py", tmp_path) is False


def test_resolve_write_target_relative_to_cwd(tmp_path: Path):
    cwd = tmp_path / "code"
    cwd.mkdir()
    assert resolve_write_target("sub/train.py", cwd) == cwd / "sub" / "train.py"


def test_resolve_write_target_absolute_passthrough(tmp_path: Path):
    absolute = tmp_path / "abs.py"
    assert resolve_write_target(str(absolute), tmp_path) == absolute


def test_validate_allows_code_root_write(tmp_path: Path):
    ws = tmp_path
    code = ws / "code"
    code.mkdir()
    (code / "train.py").write_text("x")
    assert validate_write_target("train.py", code, ws) is None


def test_validate_rejects_out_of_bounds(tmp_path: Path):
    ws = tmp_path
    code = ws / "code"
    code.mkdir()
    assert validate_write_target("../escape.py", code, ws) == "out_of_bounds_write"
    assert validate_write_target("/etc/passwd", code, ws) == "out_of_bounds_write"


def test_validate_rejects_team_memory_when_code_root_is_workspace(tmp_path: Path):
    ws = tmp_path
    (ws / "runs").mkdir()
    target = ws / "runs" / "manifest.json"
    # broad config where cwd/code_root == workspace
    assert validate_write_target(str(target), ws, ws) == "protected_team_memory_write"
