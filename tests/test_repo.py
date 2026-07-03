from mlagent.errors import MemoryRepoNotFound
from mlagent.io import read_yaml, write_yaml
from mlagent.repo import init_memory_repo, memory_status

_EXPECTED_DIRS = [
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


def test_init_creates_standard_structure(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    for relative in _EXPECTED_DIRS:
        assert (root / relative).is_dir(), relative
    profile = read_yaml(root / "project_profile/project.yaml")
    assert profile["project_name"] == "demo"
    assert (root / "skill_library/registry.yaml").exists()
    assert (root / "experience/conventions").is_dir()  # convention type supported


def test_init_is_idempotent_and_preserves_assets(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    write_yaml(root / "skill_library/registry.yaml", {"versions": [{"version": "vkeep"}]})
    # second init without force must preserve
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    assert read_yaml(root / "skill_library/registry.yaml")["versions"] == [{"version": "vkeep"}]


def test_init_force_overwrites_seed(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    write_yaml(root / "knowledge/registry.yaml", {"items": [{"id": "keep"}]})
    init_memory_repo(root, project_name="demo", primary_metric="auc", force=True)
    assert read_yaml(root / "knowledge/registry.yaml")["items"] == []


def test_status_counts(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    status = memory_status(root)
    assert status["project_name"] == "demo"
    assert status["raw_memory_count"] == 0
    assert status["experience_count"] == 0
    assert status["skill_version_count"] == 0


def test_status_missing_raises(tmp_path):
    import pytest

    with pytest.raises(MemoryRepoNotFound):
        memory_status(tmp_path / "nope")
