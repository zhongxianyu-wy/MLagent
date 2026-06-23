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


def test_search_index_filters_experience_by_confidence(tmp_path):
    from mlagent_memory.experience import add_experience
    from mlagent_memory.index import rebuild_index, search_index
    from mlagent_memory.repo import init_memory_repo
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    add_experience(root, {"id": "e_high", "type": "pitfall", "summary": "leakage high", "detail": "d", "confidence": "high", "needs_review": False, "source_raw_records": ["r"], "created_at": "2026-06-22T10:00:00+08:00"})
    add_experience(root, {"id": "e_low", "type": "pitfall", "summary": "leakage low", "detail": "d", "confidence": "low", "needs_review": False, "source_raw_records": ["r"], "created_at": "2026-06-22T10:00:00+08:00"})
    add_experience(root, {"id": "e_review", "type": "pitfall", "summary": "leakage review", "detail": "d", "confidence": "high", "needs_review": True, "source_raw_records": ["r"], "created_at": "2026-06-22T10:00:00+08:00"})
    rebuild_index(root)
    hits = search_index(root, "leakage", asset_type="experience", confidence_levels=["high", "medium"], exclude_unreviewed=True, exclude_superseded=True)
    ids = {h["asset_id"] for h in hits}
    assert "e_high" in ids
    assert "e_low" not in ids
    assert "e_review" not in ids


def test_rebuild_index_updates_registry_index_status(tmp_path):
    from mlagent_memory.io import read_yaml
    from mlagent_memory.knowledge import import_knowledge_file
    from mlagent_memory.index import rebuild_index
    from mlagent_memory.repo import init_memory_repo
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    src = tmp_path / "n.md"
    src.write_text("# AUC\nleakage prevention", encoding="utf-8")
    item = import_knowledge_file(root, src, item_type="method_note", tags=[])
    assert read_yaml(root / "project_knowledge/registry.yaml")["items"][0]["index_status"] == "pending"
    rebuild_index(root)
    assert read_yaml(root / "project_knowledge/registry.yaml")["items"][0]["index_status"] == "indexed"


def test_knowledge_search_returns_chunk_level_hits(tmp_path):
    from mlagent_memory.knowledge import import_knowledge_file
    from mlagent_memory.index import rebuild_index, search_index
    from mlagent_memory.repo import init_memory_repo
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    src = tmp_path / "paper.md"
    src.write_text("# A\nalpha\n\n# B\nbeta leakage\n", encoding="utf-8")
    import_knowledge_file(root, src, item_type="paper", tags=[])
    rebuild_index(root)
    hits = search_index(root, "leakage", asset_type="knowledge")
    assert hits
    assert "chunk_id" in hits[0]
    assert hits[0]["chunk_id"]  # non-empty chunk_id for imported knowledge
    assert hits[0]["asset_id"].startswith("know_")
    assert "leakage" in hits[0]["content"]
    assert "## Extracted Text" not in hits[0]["content"]


def test_knowledge_search_back_compat_indexes_direct_note(tmp_path):
    """A note written directly (no chunks dir) is still indexed as one doc."""
    from mlagent_memory.index import rebuild_index, search_index
    from mlagent_memory.io import write_text
    from mlagent_memory.repo import init_memory_repo
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    write_text(root / "project_knowledge/notes/know_001.md", "# Transformer\nAttention method note")
    rebuild_index(root)
    hits = search_index(root, "attention", asset_type="knowledge")
    assert len(hits) == 1
