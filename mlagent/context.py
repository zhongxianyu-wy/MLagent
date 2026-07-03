"""Assemble exploration context — progressive disclosure + relevance-filtered.

Default (summary mode): returns only {id, summary, confidence} for the top-N
most relevant entries (keyword overlap with the prompt). Conventions (code-style
base) are always included (up to limit) since they apply universally.
Use full=True for complete fields (detail, applies_when, avoid_when, etc.).
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from mlagent.io import read_text, read_yaml
from mlagent.repo import require_memory_repo


def _safe_text(path: Path) -> str:
    return read_text(path) if path.exists() else ""


def _relevance(prompt_words: set[str], text: str) -> int:
    lowered = text.lower()
    return sum(1 for w in prompt_words if w in lowered)


def assemble_context(
    root: Path,
    prompt: str,
    summary: bool = True,
    limit: int = 5,
) -> dict[str, Any]:
    """Assemble a context pack for explore-train. Default = concise + relevant top-N."""
    require_memory_repo(root)
    prompt_words = set(re.findall(r"[a-z]{2,}", prompt.lower()))

    # data understanding (brief)
    du = _safe_text(root / "data_understanding/dataset_card.md").strip()

    # scan experience layer
    experiences: list[dict[str, Any]] = []
    conventions: list[dict[str, Any]] = []
    exp_root = root / "experience"
    if exp_root.exists():
        for path in sorted(exp_root.rglob("*.yaml")):
            data = read_yaml(path)
            if data.get("superseded_by") or data.get("verified") in ("contradicted", "rolled_back"):
                continue
            if data.get("confidence") not in ("high", "medium"):
                continue
            entry = {
                "id": data.get("id"),
                "type": data.get("type"),
                "summary": data.get("summary", ""),
                "confidence": data.get("confidence"),
            }
            if not summary:
                entry["detail"] = data.get("detail", "")
                entry["applies_when"] = data.get("applies_when", [])
                entry["avoid_when"] = data.get("avoid_when", [])

            if data.get("type") == "convention":
                conventions.append(entry)
            else:
                entry["_score"] = _relevance(prompt_words, data.get("summary", "") + " " + " ".join(data.get("applies_when", [])))
                experiences.append(entry)

    # relevance-sort + limit experiences; conventions always included (universal style)
    experiences.sort(key=lambda e: -e.pop("_score", 0))
    experiences = experiences[:limit]
    conventions = conventions[:limit]

    # approved SOPs (names only)
    registry = read_yaml(root / "skill_library" / "registry.yaml")
    sops = [
        {"name": v.get("name"), "version": v.get("version")}
        for v in registry.get("versions", [])
    ]

    return {
        "current_prompt": prompt,
        "data_understanding": du,
        "experience": experiences,
        "conventions": conventions,
        "skill_versions": sops,
    }
