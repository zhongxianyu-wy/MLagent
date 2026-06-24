from typer.testing import CliRunner

from mlagent_memory.cli import app
from mlagent_memory.experience import add_experience
from mlagent_memory.index import rebuild_index, search_index
from mlagent_memory.overview import render_experience_overview, write_experience_overview
from mlagent_memory.repo import init_memory_repo


def _seed(root):
    add_experience(
        root,
        {
            "id": "e1",
            "type": "pitfall",
            "summary": "防止标签泄漏",
            "detail": "去掉后处理产生的特征",
            "confidence": "high",
            "needs_review": False,
            "source_raw_records": ["raw_memory/runs/r1.yaml"],
            "applies_when": ["表格分类", "带时间戳特征"],
            "created_at": "2026-06-24T10:00:00+08:00",
        },
    )
    add_experience(
        root,
        {
            "id": "e2",
            "type": "lesson",
            "summary": "先建立可复现基线",
            "detail": "固定随机种子与数据版本",
            "confidence": "medium",
            "needs_review": True,
            "source_raw_records": ["raw_memory/runs/r2.yaml"],
            "created_at": "2026-06-24T10:00:00+08:00",
        },
    )


def test_render_experience_overview_is_chinese_and_grouped(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    _seed(root)
    md = render_experience_overview(root)

    assert "经验总览" in md
    assert "仅供人工浏览" in md
    assert "不参与任何功能调用" in md
    # grouped by type, in display order (pitfalls first)
    assert md.index("陷阱") < md.index("经验教训")
    # content + confidence + review markers
    assert "防止标签泄漏" in md
    assert "高" in md and "中" in md
    assert "✓ 已复核" in md and "⚠️ 待复核" in md
    assert "适用场景" in md and "表格分类" in md
    # source path back to the authoritative yaml
    assert "experience/pitfalls/e1.yaml" in md
    # summary line with counts
    assert "共 **2** 条经验" in md


def test_render_experience_overview_empty_repo(tmp_path):
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    md = render_experience_overview(root)
    assert "经验总览" in md
    assert "暂无经验记录" in md


def test_overview_does_not_affect_search(tmp_path):
    """The overview MD is display-only: generating it (then rebuilding the index) must not
    change search results, and the overview file must never appear as a search hit."""
    root = tmp_path / "project_memory"
    init_memory_repo(root, project_name="demo", primary_metric="auc")
    add_experience(
        root,
        {
            "id": "e1",
            "type": "pitfall",
            "summary": "leakage pitfall here",
            "detail": "d",
            "confidence": "high",
            "needs_review": False,
            "source_raw_records": ["r"],
            "created_at": "2026-06-24T10:00:00+08:00",
        },
    )
    rebuild_index(root)
    before = search_index(root, "leakage", asset_type="experience")

    overview_path = write_experience_overview(root)  # creates experience/经验总览.md
    assert overview_path.exists()
    rebuild_index(root)  # rebuild AFTER the overview file exists
    after = search_index(root, "leakage", asset_type="experience")

    assert len(before) == len(after) == 1
    # the overview markdown must not itself be indexed / returned as a hit
    assert all("经验总览" not in h.get("source_path", "") for h in after)
    assert all(h.get("asset_type") == "experience" for h in after)


def test_cli_overview_experience(tmp_path):
    runner = CliRunner()
    root = tmp_path / "project_memory"
    runner.invoke(app, ["init", "--memory-root", str(root), "--project-name", "demo"], catch_exceptions=False)
    result = runner.invoke(app, ["overview-experience", "--memory-root", str(root)])
    assert result.exit_code == 0
    assert (root / "experience" / "经验总览.md").exists()
