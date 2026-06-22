from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from shutil import copytree, rmtree

from mlagent_memory.io import read_yaml, write_text, write_yaml
from mlagent_memory.repo import require_memory_repo
from mlagent_memory.schemas import SkillVersion


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def create_skill_candidate(
    root: Path,
    version: str,
    name: str,
    source_type: str,
    source_evidence: list[str],
) -> SkillVersion:
    require_memory_repo(root)
    candidate_dir = root / "skill_versions/.candidates" / version
    candidate_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "version": version,
        "name": name,
        "object_type": "skill_version",
        "state": "pending_review",
        "source_type": source_type,
        "source_evidence": source_evidence,
        "artifacts": [],
        "requirements": {},
        "human_review": {"reviewed": False},
        "performance": {"primary_metric": {"name": "", "value": 0.0}},
        "reproducibility": {"entrypoint": "", "required_inputs": [], "expected_outputs": []},
        "valid_from": None,
        "superseded_by": None,
    }
    candidate = SkillVersion(**data)
    write_yaml(candidate_dir / "skill.yaml", candidate.model_dump())
    write_text(candidate_dir / "reproduce.md", f"# Reproduce {name}\n")
    write_text(candidate_dir / "constraints.md", "# Constraints\n")
    write_text(candidate_dir / "validation_checklist.md", "# Validation Checklist\n")
    write_yaml(candidate_dir / "source_evidence.yaml", {"source_evidence": source_evidence})
    return candidate


def approve_skill_candidate(
    root: Path,
    version: str,
    reviewer: str,
    approval_note: str,
    performance_path: Path,
) -> SkillVersion:
    require_memory_repo(root)
    candidate_dir = root / "skill_versions/.candidates" / version
    approved_dir = root / "skill_versions" / version
    if not candidate_dir.exists():
        raise FileNotFoundError(f"SkillVersion candidate not found: {version}")
    performance = read_yaml(performance_path)
    data = read_yaml(candidate_dir / "skill.yaml")
    data["state"] = "approved"
    data["human_review"] = {
        "reviewed": True,
        "reviewer": reviewer,
        "reviewed_at": _now(),
        "approval_note": approval_note,
    }
    data["performance"] = performance
    data["valid_from"] = data["human_review"]["reviewed_at"]
    approved = SkillVersion(**data)

    if approved_dir.exists():
        rmtree(approved_dir)
    copytree(candidate_dir, approved_dir)
    write_yaml(approved_dir / "skill.yaml", approved.model_dump(exclude_none=True))
    write_yaml(approved_dir / "performance.yaml", performance)

    registry_path = root / "skill_versions/registry.yaml"
    registry = read_yaml(registry_path)
    versions = [entry for entry in registry.get("versions", []) if entry.get("version") != version]
    versions.append(
        {
            "version": version,
            "name": approved.name,
            "state": approved.state,
            "reviewer": reviewer,
            "reviewed_at": approved.human_review.reviewed_at,
            "primary_metric": performance.get("primary_metric", {}),
        }
    )
    write_yaml(registry_path, {"versions": versions})
    return approved
