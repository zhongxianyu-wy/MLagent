from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from shutil import copytree, rmtree
from typing import Any

from pydantic import ValidationError

from mlagent_memory.errors import InvalidSkillPerformance, SkillVersionNotFound
from mlagent_memory.io import read_text, read_yaml, write_text, write_yaml
from mlagent_memory.repo import require_memory_repo
from mlagent_memory.schemas import Performance, SkillVersion


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
    try:
        validated_performance = Performance(**performance)
    except ValidationError as exc:
        raise InvalidSkillPerformance(
            f"Invalid performance YAML for SkillVersion {version}: {exc}"
        ) from exc
    data = read_yaml(candidate_dir / "skill.yaml")
    data["state"] = "approved"
    data["human_review"] = {
        "reviewed": True,
        "reviewer": reviewer,
        "reviewed_at": _now(),
        "approval_note": approval_note,
    }
    data["performance"] = validated_performance.model_dump()
    data["valid_from"] = data["human_review"]["reviewed_at"]
    approved = SkillVersion(**data)

    if approved_dir.exists():
        rmtree(approved_dir)
    copytree(candidate_dir, approved_dir)
    write_yaml(approved_dir / "skill.yaml", approved.model_dump(exclude_none=True))
    write_yaml(approved_dir / "performance.yaml", validated_performance.model_dump())

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
            "primary_metric": validated_performance.model_dump()["primary_metric"],
        }
    )
    write_yaml(registry_path, {"versions": versions})
    return approved


def list_skills(root: Path) -> list[dict[str, Any]]:
    require_memory_repo(root)
    registry = read_yaml(root / "skill_versions/registry.yaml")
    return list(registry.get("versions", []))


def _read_skill_bundle(directory: Path, version: str, source: str) -> dict[str, Any]:
    skill = read_yaml(directory / "skill.yaml")
    files: dict[str, str] = {}
    for fname in ("reproduce.md", "constraints.md", "validation_checklist.md", "performance.yaml"):
        path = directory / fname
        if path.exists():
            files[fname] = read_text(path)
    return {
        "version": version,
        "source": source,
        "state": skill.get("state"),
        "name": skill.get("name"),
        "skill": skill,
        "files": files,
    }


def get_skill(root: Path, version: str, include_draft: bool = False) -> dict[str, Any]:
    require_memory_repo(root)
    approved_dir = root / "skill_versions" / version
    candidate_dir = root / "skill_versions/.candidates" / version
    if (approved_dir / "skill.yaml").exists():
        return _read_skill_bundle(approved_dir, version, "approved")
    if (candidate_dir / "skill.yaml").exists():
        if not include_draft:
            raise SkillVersionNotFound(
                f"SkillVersion {version} is a pending candidate, not approved. "
                "Pass --include-draft to inspect the draft."
            )
        return _read_skill_bundle(candidate_dir, version, "candidate")
    raise SkillVersionNotFound(f"SkillVersion not found: {version}")
