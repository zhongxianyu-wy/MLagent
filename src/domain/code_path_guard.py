"""Pure code-path jail predicate — shared by the PreToolUse write hook and DomainCore.

No DomainCore dependency, no I/O mutation. The hook (an external Claude Code
subprocess) and the domain core both need the same notion of "this write target
is inside the managed code root and is not a protected Team Memory asset", so it
lives here as pure functions.
"""
from __future__ import annotations

from pathlib import Path

# Team Memory namespaces that an agent may NEVER write directly — those writes
# must go through DomainCore (e.g. ``save_code_revision``). Kept relative to the
# workspace root.
TEAM_MEMORY_NAMESPACES = frozenset(
    {
        "runs",
        "code-revisions",
        "datasets",
        "experiences",
        "sops",
        "sessions",
        "notebooks",
        ".mlagent-local",
        "knowledge",
    }
)


def resolve_write_target(file_path: str, cwd: Path) -> Path:
    """Resolve a tool's ``file_path`` (relative to ``cwd`` or absolute)."""
    path = Path(file_path)
    if path.is_absolute():
        return path
    return cwd / path


def is_within_code_root(target: Path, code_root: Path) -> bool:
    """True if ``target`` resolves inside ``code_root`` (no symlink, no escape)."""
    try:
        root = code_root.expanduser().resolve(strict=False)
        if target.is_symlink():
            return False
        resolved = target.expanduser().resolve(strict=False)
        resolved.relative_to(root)
    except (ValueError, OSError):
        return False
    return True


def is_team_memory_path(target: Path, workspace: Path) -> bool:
    """True if ``target`` lands in a protected Team Memory namespace under ``workspace``."""
    try:
        resolved = target.expanduser().resolve(strict=False)
        ws = workspace.expanduser().resolve(strict=False)
        relative = resolved.relative_to(ws)
    except (ValueError, OSError):
        return False
    parts = relative.parts
    return bool(parts) and parts[0] in TEAM_MEMORY_NAMESPACES


def validate_write_target(
    file_path: str,
    cwd: Path,
    workspace: Path,
) -> str | None:
    """Return a denial reason code, or ``None`` if the write is allowed.

    Order: (1) the target must be inside ``cwd`` (the managed code root);
    (2) it must not land in a protected Team Memory namespace. Either failure
    short-circuits with the corresponding code.
    """
    target = resolve_write_target(file_path, cwd)
    if not is_within_code_root(target, cwd):
        return "out_of_bounds_write"
    if is_team_memory_path(target, workspace):
        return "protected_team_memory_write"
    return None
