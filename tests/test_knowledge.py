from mlagent_memory.io import read_yaml
from mlagent_memory.knowledge import import_knowledge_file
from mlagent_memory.repo import init_memory_repo


def test_import_markdown_copies_original_and_creates_note(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    source = tmp_path / "method.md"
    source.write_text("# Method\nFeature selection notes", encoding="utf-8")

    item = import_knowledge_file(root, source, item_type="method_note", tags=["feature"])

    assert item.type == "method_note"
    assert (root / item.stored_path).exists()
    assert (root / "project_knowledge/notes" / f"{item.id}.md").exists()
    registry = read_yaml(root / "project_knowledge/registry.yaml")
    assert registry["items"][0]["id"] == item.id


def test_import_rejects_unsupported_suffix(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    source = tmp_path / "data.xlsx"
    source.write_text("binary", encoding="utf-8")

    try:
        import_knowledge_file(root, source, item_type="data_doc", tags=[])
    except ValueError as exc:
        assert "Unsupported knowledge file type" in str(exc)
    else:
        raise AssertionError("Expected unsupported file type failure")


def test_import_knowledge_writes_chunks_and_manifest(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    src = tmp_path / "paper.md"
    src.write_text("# A\nalpha\n\n# B\nbeta leakage\n", encoding="utf-8")
    item = import_knowledge_file(root, src, item_type="paper", tags=[])
    chunk_dir = root / "project_knowledge/chunks" / item.id
    assert chunk_dir.exists()
    assert (chunk_dir / "manifest.yaml").exists()
    chunk_files = sorted(chunk_dir.glob("chunk_*.md"))
    assert len(chunk_files) >= 2  # two markdown sections -> at least 2 chunks
