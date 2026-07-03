"""Assemble exploration context (experience injection for explore-train).

Reads the experience layer (filtered: high/medium confidence, not contradicted/
superseded) + code conventions + SOP list + data understanding → a structured
pack that explore-train injects so Claude writes code grounded in project style.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from mlagent.io import read_text, read_yaml
from mlagent.repo import require_memory_repo


def _safe_text(path: Path) -> str:
    return read_text(path) if path.exists() else ""


def assemble_context(root: Path, prompt: str) -> dict[str, Any]:
    require_memory_repo(root)

    # data understanding
    du = "\n".join([
        _safe_text(root / "data_understanding/dataset_card.md"),
        _safe_text(root / "data_understanding/label_definition.md"),
    ]).strip()

    # experience (filtered) + conventions (code-style base)
    experiences: list[dict[str, Any]] = []
    conventions: list[dict[str, Any]] = []
    exp_root = root / "experience"
    if exp_root.exists():
        for path in sorted(exp_root.rglob("*.yaml")):
            data = read_yaml(path)
            if data.get("superseded_by"):
                continue
            if data.get("verified") in ("contradicted", "rolled_back"):
                continue
            if data.get("confidence") not in ("high", "medium"):
                continue
            entry = {
                "id": data.get("id"),
                "type": data.get("type"),
                "summary": data.get("summary", ""),
                "detail": data.get("detail", ""),
                "confidence": data.get("confidence"),
                "applies_when": data.get("applies_when", []),
                "avoid_when": data.get("avoid_when", []),
            }
            if data.get("type") == "convention":
                conventions.append(entry)
            else:
                experiences.append(entry)

    # approved SOPs
    registry = read_yaml(root / "skill_library" / "registry.yaml")
    sops = [
        {"name": v.get("name"), "version": v.get("version"), "state": v.get("state")}
        for v in registry.get("versions", [])
    ]

    return {
        "current_prompt": prompt,
        "data_understanding": du,
        "experience": experiences,
        "conventions": conventions,
        "skill_versions": sops,
    }
