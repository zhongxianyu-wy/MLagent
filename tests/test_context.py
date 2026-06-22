from mlagent_memory.context import create_context_pack
from mlagent_memory.experience import add_experience
from mlagent_memory.index import rebuild_index
from mlagent_memory.io import write_text
from mlagent_memory.repo import init_memory_repo


def test_exploration_pack_orders_sections_by_confirmed_priority(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    write_text(root / "data_understanding/dataset_card.md", "Fields include age and tumor_stage.")
    add_experience(
        root,
        {
            "id": "exp_001",
            "type": "pitfall",
            "summary": "Leakage risk",
            "detail": "Do not keep post outcome fields.",
            "confidence": "high",
            "needs_review": False,
            "source_raw_records": ["raw_memory/runs/raw_001.yaml"],
            "created_at": "2026-06-22T10:30:00+08:00",
        },
    )
    write_text(root / "project_knowledge/notes/know_001.md", "AUC optimization knowledge")
    rebuild_index(root)

    pack = create_context_pack(root, pack_type="exploration", prompt="Improve AUC")
    names = [section["name"] for section in pack.sections]
    assert names[:5] == [
        "current_prompt",
        "data_understanding",
        "experience",
        "project_knowledge",
        "skill_versions",
    ]


def test_retraining_pack_requires_skill_version(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    try:
        create_context_pack(root, pack_type="retraining", prompt="Retrain", skill_version="v999")
    except FileNotFoundError as exc:
        assert "SkillVersion not found" in str(exc)
    else:
        raise AssertionError("Expected missing SkillVersion failure")
