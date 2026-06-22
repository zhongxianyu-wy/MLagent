from mlagent_memory.io import read_yaml
from mlagent_memory.repo import init_memory_repo, memory_status


def test_init_memory_repo_creates_standard_structure(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")

    expected_dirs = [
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
    for relative in expected_dirs:
        assert (root / relative).is_dir()

    profile = read_yaml(root / "project_profile/project.yaml")
    assert profile["project_name"] == "demo"
    assert profile["primary_metric"] == "auc"
    assert (root / "skill_versions/registry.yaml").exists()


def test_memory_status_counts_assets(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    status = memory_status(root)
    assert status["project_name"] == "demo"
    assert status["raw_memory_count"] == 0
    assert status["experience_count"] == 0
    assert status["skill_version_count"] == 0
