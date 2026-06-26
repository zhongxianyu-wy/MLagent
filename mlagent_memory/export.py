"""Read-only memory snapshot for frontend visualization (display-only).

Produces a derived JSON view of the memory repo: project, knowledge, runs (timeline),
experience (grouped), skills (approved + candidates), links (graph edges), a merged
timeline, and per-metric time series. Never written to by any functional path; like the
FTS index, it is a rebuildable projection of the YAML/Markdown source of truth.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from mlagent_memory.io import read_yaml
from mlagent_memory.repo import require_memory_repo

_RAW_MEMORY_SUBDIRS = ("sessions", "explorations", "runs", "human_notes")
_EXPERIENCE_TYPES = ("lesson", "pitfall", "successful_pattern", "failed_direction")


def _safe_yaml(path: Path) -> dict[str, Any]:
    return read_yaml(path) if path.exists() else {}


def _project_run(record: dict[str, Any]) -> dict[str, Any]:
    commands = [
        {"summary": c.get("summary"), "status": c.get("status")}
        for c in (record.get("commands") or [])
    ]
    return {
        "id": record.get("id"),
        "type": record.get("type"),
        "created_at": record.get("created_at"),
        "session_id": record.get("session_id"),
        "goal": record.get("goal"),
        "commands": commands,
        "results": record.get("results") or {},
        "failure_reason": record.get("failure_reason"),
    }


def _project_experience(record: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": record.get("id"),
        "confidence": record.get("confidence"),
        "needs_review": record.get("needs_review"),
        "summary": record.get("summary"),
        "source_raw_records": record.get("source_raw_records") or [],
        "superseded_by": record.get("superseded_by"),
        "created_at": record.get("created_at"),
    }


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def export_memory_snapshot(root: Path) -> dict[str, Any]:
    """Build the full read-only snapshot dict for frontend visualization."""
    require_memory_repo(root)
    root = Path(root)

    profile = _safe_yaml(root / "project_profile/project.yaml")
    data_versions = _safe_yaml(root / "data_understanding/data_versions.yaml")
    schema = _safe_yaml(root / "data_understanding/schema.yaml")
    knowledge_registry = _safe_yaml(root / "project_knowledge/registry.yaml")

    # knowledge items + chunk counts
    knowledge_items = []
    for item in knowledge_registry.get("items", []):
        know_id = item.get("id")
        chunk_dir = root / "project_knowledge/chunks" / know_id if know_id else None
        chunk_count = len(list(chunk_dir.glob("chunk_*.md"))) if chunk_dir and chunk_dir.exists() else 0
        knowledge_items.append({
            "id": know_id,
            "type": item.get("type"),
            "title": item.get("title"),
            "index_status": item.get("index_status"),
            "tags": item.get("tags") or [],
            "chunk_count": chunk_count,
        })

    # runs (flat, all raw_memory subdirs)
    runs_raw: list[dict[str, Any]] = []
    for sub in _RAW_MEMORY_SUBDIRS:
        sub_dir = root / "raw_memory" / sub
        if sub_dir.exists():
            for path in sorted(sub_dir.glob("*.yaml")):
                runs_raw.append(read_yaml(path))
    runs = [_project_run(r) for r in runs_raw]

    # experience grouped by type
    experience: dict[str, list[dict[str, Any]]] = {t: [] for t in _EXPERIENCE_TYPES}
    exp_dir = root / "experience"
    if exp_dir.exists():
        for path in sorted(exp_dir.rglob("*.yaml")):
            rec = read_yaml(path)
            rtype = rec.get("type")
            if rtype in experience:
                experience[rtype].append(_project_experience(rec))

    # skills
    registry = _safe_yaml(root / "skill_versions/registry.yaml")
    approved = [
        {
            "version": v.get("version"),
            "name": v.get("name"),
            "state": v.get("state"),
            "reviewer": v.get("reviewer"),
            "reviewed_at": v.get("reviewed_at"),
            "primary_metric": v.get("primary_metric"),
        }
        for v in registry.get("versions", [])
    ]
    candidates = []
    cand_root = root / "skill_versions/.candidates"
    if cand_root.exists():
        for cand_dir in sorted(cand_root.iterdir()):
            skill_yaml = cand_dir / "skill.yaml"
            if not skill_yaml.exists():
                continue
            version = cand_dir.name
            # skip candidates that have already been approved (their candidate dir is retained as history)
            if (root / "skill_versions" / version / "skill.yaml").exists():
                continue
            sk = read_yaml(skill_yaml)
            candidates.append({
                "version": sk.get("version"),
                "name": sk.get("name"),
                "state": sk.get("state"),
                "source_type": sk.get("source_type"),
                "source_evidence": sk.get("source_evidence") or [],
                "has_skill_md": (cand_dir / "SKILL.md").exists(),
            })

    # links (graph edges)
    links: list[dict[str, str]] = []
    for rtype, records in experience.items():
        for rec in records:
            for src in rec["source_raw_records"]:
                links.append({"source": f"experience:{rec['id']}", "target": f"raw:{src}", "kind": "experience_derives_from"})
    for run in runs:
        if run.get("session_id"):
            links.append({"source": f"run:{run['id']}", "target": f"session:{run['session_id']}", "kind": "run_in_session"})
    for cand in candidates:
        for ev in cand["source_evidence"]:
            links.append({"source": f"skill:{cand['version']}", "target": f"evidence:{ev}", "kind": "skill_evidence"})
    for v in approved:
        # approved skills keep source_evidence in their skill.yaml; surface via registry note only
        pass

    # timeline (chronological events)
    timeline: list[dict[str, Any]] = []
    for run in runs:
        if run.get("created_at"):
            timeline.append({"ts": run["created_at"], "kind": "run", "ref": run["id"], "label": run.get("goal") or run["id"]})
    for records in experience.values():
        for rec in records:
            if rec.get("created_at"):
                timeline.append({"ts": rec["created_at"], "kind": "experience", "ref": rec["id"], "label": rec["summary"]})
    for v in approved:
        if v.get("reviewed_at"):
            timeline.append({"ts": v["reviewed_at"], "kind": "skill", "ref": v["version"], "label": v["name"]})
    timeline.sort(key=lambda e: str(e["ts"]))

    # metric time series from run results
    metric_series: dict[str, list[dict[str, Any]]] = {}
    for run in runs:
        results = run.get("results") or {}
        for name, value in results.items():
            if _is_number(value):
                metric_series.setdefault(name, []).append(
                    {"run_id": run["id"], "created_at": run.get("created_at"), "value": value}
                )

    return {
        "project": {
            "name": profile.get("project_name"),
            "primary_metric": profile.get("primary_metric"),
            "task_type": profile.get("task_type"),
        },
        "data_understanding": {
            "schema": schema,
            "data_versions": data_versions,
            "has_dataset_card": (root / "data_understanding/dataset_card.md").exists(),
            "has_label_definition": (root / "data_understanding/label_definition.md").exists(),
        },
        "knowledge": knowledge_items,
        "runs": runs,
        "experience": experience,
        "skills": {"approved": approved, "candidates": candidates},
        "links": links,
        "timeline": timeline,
        "metric_series": metric_series,
    }
