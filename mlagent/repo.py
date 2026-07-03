"""project_memory/ initialization and status."""

from __future__ import annotations

from pathlib import Path

from mlagent.errors import MemoryRepoNotFound
from mlagent.io import read_yaml, write_text, write_yaml

# Three-layer memory dir tree (clarified design §2.1).
STANDARD_DIRS = [
    "project_profile",
    "data_understanding",
    "knowledge/originals",
    "knowledge/notes",
    "knowledge/chunks",
    "raw_memory/sessions",
    "raw_memory/explorations",
    "raw_memory/runs",
    "raw_memory/human_notes",
    "experience/lessons",
    "experience/pitfalls",
    "experience/successful_patterns",
    "experience/failed_directions",
    "experience/conventions",
    "skill_library",
    "indexes",
]


def init_memory_repo(root: Path, project_name: str, primary_metric: str, force: bool = False) -> None:
    """Create the standard memory tree. Idempotent: only writes a seed file if it is
    missing, unless force=True (overwrite all seed files). Directories are always mkdir -p."""
    for relative in STANDARD_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)

    _seed_yaml(root / "project_profile/project.yaml", {
        "project_name": project_name,
        "task_type": "tabular_ml",
        "primary_metric": primary_metric,
        "memory_version": "0.1.0",
    }, force)
    write_text(root / "project_profile/objectives.md", f"# {project_name} Objectives\n")
    _seed_text(root / "data_understanding/dataset_card.md", "# Dataset Card\n", force)
    _seed_yaml(root / "data_understanding/schema.yaml", {"fields": []}, force)
    _seed_text(root / "data_understanding/label_definition.md", "# Label Definition\n", force)
    _seed_yaml(root / "data_understanding/data_versions.yaml", {"versions": []}, force)
    _seed_yaml(root / "knowledge/registry.yaml", {"items": []}, force)
    _seed_yaml(root / "skill_library/registry.yaml", {"versions": []}, force)


def _seed_yaml(path: Path, data: dict, force: bool) -> None:
    if force or not path.exists():
        write_yaml(path, data)


def _seed_text(path: Path, content: str, force: bool) -> None:
    if force or not path.exists():
        write_text(path, content)


def require_memory_repo(root: Path) -> None:
    if not root.exists() or not (root / "project_profile/project.yaml").exists():
        raise MemoryRepoNotFound(f"Project memory repo does not exist: {root}")


def _count_yaml(root: Path, relative: str) -> int:
    folder = root / relative
    if not folder.exists():
        return 0
    return sum(1 for path in folder.rglob("*.yaml") if path.is_file())


def memory_status(root: Path) -> dict[str, object]:
    require_memory_repo(root)
    profile = read_yaml(root / "project_profile/project.yaml")
    registry = read_yaml(root / "skill_library/registry.yaml")
    return {
        "project_name": profile["project_name"],
        "primary_metric": profile["primary_metric"],
        "raw_memory_count": _count_yaml(root, "raw_memory"),
        "experience_count": _count_yaml(root, "experience"),
        "skill_version_count": len(registry.get("versions", [])),
    }
