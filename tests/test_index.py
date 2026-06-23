from mlagent_memory.index import rebuild_index, search_index
from mlagent_memory.io import write_text, write_yaml
from mlagent_memory.repo import init_memory_repo


def test_rebuild_index_and_search_experience(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    write_yaml(
        root / "experience/pitfalls/exp_001.yaml",
        {
            "id": "exp_001",
            "type": "pitfall",
            "object_type": "experience",
            "summary": "Target leakage from post outcome fields",
            "detail": "Remove post outcome fields before training.",
            "confidence": "high",
            "needs_review": False,
            "source_raw_records": ["raw_memory/runs/raw_001.yaml"],
            "created_at": "2026-06-22T10:00:00+08:00",
        },
    )

    rebuild_index(root)
    hits = search_index(root, "leakage", asset_type="experience")
    assert len(hits) == 1
    assert hits[0]["asset_id"] == "exp_001"


def test_rebuild_index_and_search_knowledge_note(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    write_text(root / "project_knowledge/notes/know_001.md", "# Transformer\nAttention method note")

    rebuild_index(root)
    hits = search_index(root, "attention", asset_type="knowledge")
    assert len(hits) == 1
    assert hits[0]["asset_type"] == "knowledge"


def test_search_index_returns_empty_when_no_index(tmp_path):
    from mlagent_memory.index import search_index
    from mlagent_memory.repo import init_memory_repo
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    # No rebuild_index call -> no FTS index exists.
    assert search_index(root, "anything") == []
    assert search_index(root, "leakage", asset_type="experience") == []
