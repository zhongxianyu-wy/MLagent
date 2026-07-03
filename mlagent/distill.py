"""Distill Curator (deterministic, no LLM).

The distill-experience SKILL (Claude) reflects on raw_memory and produces a
distill plan (a list of ops). This module APPLIES that plan deterministically:
insert / update / link / supersede / noop. The LLM decides what; we decide how.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from pydantic import BaseModel

from mlagent.experience import add_experience
from mlagent.io import read_yaml, write_yaml
from mlagent.repo import require_memory_repo


class DistillOp(BaseModel):
    decision: str  # insert|update|link|supersede|noop — validated in apply
    experience: dict[str, Any] | None = None  # for insert/link/supersede
    target_id: str | None = None  # existing exp id for update/link/supersede
    patch: dict[str, Any] | None = None  # for update


def _find_experience_path(root: Path, exp_id: str) -> Path | None:
    exp_root = root / "experience"
    if not exp_root.exists():
        return None
    for path in exp_root.rglob("*.yaml"):
        data = read_yaml(path)
        if data.get("id") == exp_id:
            return path
    return None


def apply_distill_plan(root: Path, ops: list[dict[str, Any]]) -> dict[str, int]:
    """Apply a distill plan deterministically. Returns a summary count per decision."""
    require_memory_repo(root)
    summary = {"insert": 0, "update": 0, "link": 0, "supersede": 0, "noop": 0, "error": 0}
    for raw_op in ops:
        op = DistillOp(**raw_op)
        decision = op.decision
        if decision not in summary:
            summary["error"] += 1
            continue
        try:
            if decision == "noop":
                pass
            elif decision == "insert":
                add_experience(root, op.experience or {})
            elif decision == "update":
                _apply_update(root, op.target_id, op.patch or {})
            elif decision == "link":
                rec = add_experience(root, op.experience or {})
                _add_related(root, op.target_id, rec.id)
            elif decision == "supersede":
                rec = add_experience(root, op.experience or {})
                _mark_superseded(root, op.target_id, rec.id)
            summary[decision] += 1
        except Exception:
            summary["error"] += 1
    return summary


def _apply_update(root: Path, target_id: str | None, patch: dict[str, Any]) -> None:
    if not target_id:
        raise ValueError("update requires target_id")
    path = _find_experience_path(root, target_id)
    if not path:
        raise FileNotFoundError(f"Experience not found: {target_id}")
    data = read_yaml(path)
    data.update(patch)
    write_yaml(path, data)


def _add_related(root: Path, target_id: str | None, new_id: str) -> None:
    if not target_id:
        return
    path = _find_experience_path(root, target_id)
    if not path:
        return
    data = read_yaml(path)
    related = data.get("related") or []
    if new_id not in related:
        related.append(new_id)
    data["related"] = related
    write_yaml(path, data)


def _mark_superseded(root: Path, target_id: str | None, new_id: str) -> None:
    if not target_id:
        return
    path = _find_experience_path(root, target_id)
    if not path:
        return
    data = read_yaml(path)
    data["superseded_by"] = new_id
    data["verified"] = "rolled_back"
    write_yaml(path, data)
