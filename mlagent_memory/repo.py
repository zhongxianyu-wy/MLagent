from __future__ import annotations

from pathlib import Path

from mlagent_memory.io import read_yaml, write_text, write_yaml


STANDARD_DIRS = [
    "project_profile",
    "data_understanding",
    "project_knowledge/docs",
    "project_knowledge/papers",
    "project_knowledge/notes",
    "project_knowledge/originals",
    "raw_memory/sessions",
    "raw_memory/explorations",
    "raw_memory/runs",
    "raw_memory/human_notes",
    "experience/lessons",
    "experience/pitfalls",
    "experience/successful_patterns",
    "experience/failed_directions",
    "skill_versions",
    "indexes",
]


def init_memory_repo(root: Path, project_name: str, primary_metric: str, force: bool = False) -> None:
    for relative in STANDARD_DIRS:
        (root / relative).mkdir(parents=True, exist_ok=True)

    profile_path = root / "project_profile/project.yaml"
    if force or not profile_path.exists():
        write_yaml(
            profile_path,
            {
                "project_name": project_name,
                "task_type": "tabular_ml",
                "primary_metric": primary_metric,
                "memory_version": "0.1.0",
            },
        )
    objectives_path = root / "project_profile/objectives.md"
    if force or not objectives_path.exists():
        write_text(objectives_path, f"# {project_name} Objectives\n")
    dataset_card_path = root / "data_understanding/dataset_card.md"
    if force or not dataset_card_path.exists():
        write_text(dataset_card_path, "# Dataset Card\n")
    schema_path = root / "data_understanding/schema.yaml"
    if force or not schema_path.exists():
        write_yaml(schema_path, {"fields": []})
    label_def_path = root / "data_understanding/label_definition.md"
    if force or not label_def_path.exists():
        write_text(label_def_path, "# Label Definition\n")
    data_versions_path = root / "data_understanding/data_versions.yaml"
    if force or not data_versions_path.exists():
        write_yaml(data_versions_path, {"versions": []})
    knowledge_registry_path = root / "project_knowledge/registry.yaml"
    if force or not knowledge_registry_path.exists():
        write_yaml(knowledge_registry_path, {"items": []})
    skill_registry_path = root / "skill_versions/registry.yaml"
    if force or not skill_registry_path.exists():
        write_yaml(skill_registry_path, {"versions": []})


def require_memory_repo(root: Path) -> None:
    if not root.exists():
        from mlagent_memory.errors import MemoryRepoNotFound

        raise MemoryRepoNotFound(f"Project memory repo does not exist: {root}")
    if not (root / "project_profile/project.yaml").exists():
        from mlagent_memory.errors import MemoryRepoNotFound

        raise MemoryRepoNotFound(f"Invalid project memory repo: {root}")


def _count_yaml(root: Path, relative: str) -> int:
    folder = root / relative
    if not folder.exists():
        return 0
    return sum(1 for path in folder.rglob("*.yaml") if path.is_file())


def memory_status(root: Path) -> dict[str, object]:
    require_memory_repo(root)
    profile = read_yaml(root / "project_profile/project.yaml")
    registry = read_yaml(root / "skill_versions/registry.yaml")
    return {
        "project_name": profile["project_name"],
        "primary_metric": profile["primary_metric"],
        "raw_memory_count": _count_yaml(root, "raw_memory"),
        "experience_count": _count_yaml(root, "experience"),
        "skill_version_count": len(registry.get("versions", [])),
    }
