from __future__ import annotations

from pathlib import Path
from typing import Any

from mlagent_memory.io import read_yaml, write_text
from mlagent_memory.repo import require_memory_repo

# Display-only projection of the experience layer into Chinese Markdown.
# This file is NOT read by any functional path (index, context-pack, search).
# The authoritative source remains experience/**/*.yaml.

_OVERVIEW_FILENAME = "经验总览.md"

# (record type, Chinese heading, one-line description) — display order matters.
_TYPE_GROUPS: list[tuple[str, str, str]] = [
    ("pitfall", "陷阱", "踩过的坑，优先避免重犯"),
    ("lesson", "经验教训", "提炼出的通用规律"),
    ("successful_pattern", "成功模式", "已验证有效的做法"),
    ("failed_direction", "失败方向", "尝试过但不可行的方向"),
]

_CONFIDENCE_LABEL = {"high": "高", "medium": "中", "low": "低"}

_HEADER = (
    "# 经验总览\n\n"
    "> 本文件由 `mlagent-memory overview-experience` 自动生成，**仅供人工浏览**。\n"
    "> 事实源为 `experience/**/*.yaml`；请勿手动编辑——下次运行命令会覆盖本文件。\n"
    "> 本文件不参与任何功能调用（不被索引、不进入 Context Pack、不被检索）。\n"
)


def _collect_records(root: Path) -> list[dict[str, Any]]:
    exp_root = root / "experience"
    records: list[dict[str, Any]] = []
    if not exp_root.exists():
        return records
    for path in sorted(exp_root.rglob("*.yaml")):
        data = read_yaml(path)
        data["_source_path"] = str(path.relative_to(root))
        records.append(data)
    return records


def _render_record(record: dict[str, Any]) -> str:
    rid = record.get("id", "?")
    confidence = _CONFIDENCE_LABEL.get(str(record.get("confidence", "")), str(record.get("confidence", "")))
    review = " ｜ ⚠️ 待复核" if record.get("needs_review") else " ｜ ✓ 已复核"
    superseded = record.get("superseded_by")
    title = f"### `{rid}` · 置信度 {confidence}{review}"
    if superseded:
        title += f" ｜ ~~已废弃（被 `{superseded}` 取代）~~"

    lines = [title, ""]
    if record.get("summary"):
        lines.append(f"**摘要**：{record['summary']}")
    if record.get("detail"):
        lines.append(f"**详情**：{record['detail']}")
    applies = record.get("applies_when") or []
    if applies:
        lines.append(f"**适用场景**：{'；'.join(str(x) for x in applies)}")
    avoid = record.get("avoid_when") or []
    if avoid:
        lines.append(f"**应避免**：{'；'.join(str(x) for x in avoid)}")
    sources = record.get("source_raw_records") or []
    if sources:
        lines.append(f"**证据来源**：{'，'.join(str(x) for x in sources)}")
    methods = record.get("related_methods") or []
    if methods:
        lines.append(f"**相关方法**：{'，'.join(str(x) for x in methods)}")
    lines.append(f"— `{record.get('_source_path')}`")
    return "\n".join(lines)


def render_experience_overview(root: Path) -> str:
    """Render all experience records into a Chinese Markdown digest for human browsing only."""
    require_memory_repo(root)
    records = _collect_records(root)

    if not records:
        return "\n".join([
            _HEADER,
            "_暂无经验记录。先用 `mlagent-memory add-experience <record.yaml>` 沉淀经验，再重新生成。_\n",
        ])

    by_type: dict[str, list[dict[str, Any]]] = {key: [] for key, _, _ in _TYPE_GROUPS}
    for record in records:
        rtype = record.get("type")
        if rtype in by_type:
            by_type[rtype].append(record)

    conf_counts = {"high": 0, "medium": 0, "low": 0}
    unreviewed = 0
    for record in records:
        conf = record.get("confidence")
        if conf in conf_counts:
            conf_counts[conf] += 1
        if record.get("needs_review"):
            unreviewed += 1

    lines = [
        _HEADER,
        f"共 **{len(records)}** 条经验 ｜ 置信度 高 {conf_counts['high']} / 中 {conf_counts['medium']} / 低 {conf_counts['low']}"
        f" ｜ 待复核 {unreviewed}\n",
    ]
    for key, heading, desc in _TYPE_GROUPS:
        items = by_type[key]
        if not items:
            continue
        lines.append(f"## {heading}（{key}）\n")
        lines.append(f"_{desc} · 共 {len(items)} 条_\n")
        for record in items:
            lines.append(_render_record(record))
            lines.append("")
    return "\n".join(lines)


def write_experience_overview(root: Path) -> Path:
    """Render the experience overview and write it to experience/<overview>. Returns the path."""
    path = root / "experience" / _OVERVIEW_FILENAME
    write_text(path, render_experience_overview(root))
    return path
