from __future__ import annotations

from pathlib import Path

from mlagent_memory.index import search_index
from mlagent_memory.io import read_text, read_yaml
from mlagent_memory.repo import require_memory_repo
from mlagent_memory.schemas import ContextPack


def _safe_text(path: Path) -> str:
    return read_text(path) if path.exists() else ""


def _skill_versions_list(root: Path) -> list[dict[str, object]]:
    registry_path = root / "skill_versions/registry.yaml"
    if not registry_path.exists():
        return []
    return list(read_yaml(registry_path).get("versions", []))


def _exploration_pack(root: Path, prompt: str) -> ContextPack:
    sections = [
        {"name": "current_prompt", "content": prompt},
        {
            "name": "data_understanding",
            "content": "\n\n".join(
                [
                    _safe_text(root / "data_understanding/dataset_card.md"),
                    _safe_text(root / "data_understanding/label_definition.md"),
                ]
            ).strip(),
        },
        {"name": "experience", "content": search_index(root, prompt, asset_type="experience", limit=5)},
        {"name": "project_knowledge", "content": search_index(root, prompt, asset_type="knowledge", limit=5)},
        {"name": "skill_versions", "content": _skill_versions_list(root)},
    ]
    return ContextPack(pack_type="exploration", prompt=prompt, sections=sections)


def _retraining_pack(root: Path, prompt: str, skill_version: str) -> ContextPack:
    version_dir = root / "skill_versions" / skill_version
    if not version_dir.exists():
        raise FileNotFoundError(f"SkillVersion not found: {skill_version}")
    sections = [
        {"name": "current_prompt", "content": prompt},
        {"name": "skill_version", "content": _safe_text(version_dir / "reproduce.md")},
        {"name": "constraints", "content": _safe_text(version_dir / "constraints.md")},
        {"name": "validation_checklist", "content": _safe_text(version_dir / "validation_checklist.md")},
        {"name": "data_understanding", "content": _safe_text(root / "data_understanding/dataset_card.md")},
    ]
    return ContextPack(pack_type="retraining", prompt=prompt, sections=sections)


def create_context_pack(
    root: Path,
    pack_type: str,
    prompt: str,
    skill_version: str | None = None,
) -> ContextPack:
    require_memory_repo(root)
    if pack_type == "exploration":
        return _exploration_pack(root, prompt)
    if pack_type == "retraining":
        if not skill_version:
            raise ValueError("Retraining Context Pack requires skill_version")
        return _retraining_pack(root, prompt, skill_version)
    if pack_type in {"distillation", "skill_candidate"}:
        return ContextPack(pack_type=pack_type, prompt=prompt, sections=[{"name": "current_prompt", "content": prompt}])
    raise ValueError(f"Unknown context pack type: {pack_type}")
