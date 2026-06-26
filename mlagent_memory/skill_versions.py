from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from shutil import copytree, move
from typing import Any

from pydantic import ValidationError

from mlagent_memory.errors import InvalidSkillPerformance, SkillVersionAlreadyExists, SkillVersionNotFound
from mlagent_memory.io import read_text, read_yaml, write_text, write_yaml
from mlagent_memory.repo import require_memory_repo
from mlagent_memory.schemas import Performance, SkillVersion
from mlagent_memory.skill_extraction import (
    analyze_training_logic,
    parse_source,
    render_skill_md,
    resolve_source_evidence,
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _source_rel(root: Path, src_path: Path) -> str:
    try:
        return str(src_path.resolve().relative_to(Path(root).resolve().parent))
    except ValueError:
        return src_path.name


def _reproduce_reference(name: str) -> str:
    return (
        f"# Reproduce {name}\n\n"
        "This SkillVersion was generated from a source notebook/script. "
        "See `SKILL.md` for the extracted feature-selection + training recipe, "
        "and `references/source.py` for the authoritative runnable source.\n"
    )


def _enrich_candidate_from_source(
    candidate_dir: Path,
    root: Path,
    data: dict[str, Any],
    version: str,
    name: str,
    source_type: str,
    source_evidence: list[str],
) -> bool:
    """Parse the source notebook/script into a skill-creator-format SKILL.md + references.
    Mutates `data` (artifacts/requirements/reproducibility). Returns False (no-op) if no
    resolvable source or parsing fails — caller keeps the empty-stub behavior."""
    src_path = resolve_source_evidence(root, source_evidence)
    if src_path is None:
        return False
    try:
        parsed = parse_source(src_path)
        analysis = analyze_training_logic(parsed["code"])
        skill_md = render_skill_md(version, name, source_type, analysis, _source_rel(root, src_path))
    except (ValueError, OSError):
        return False
    refs = candidate_dir / "references"
    refs.mkdir(parents=True, exist_ok=True)
    write_text(candidate_dir / "SKILL.md", skill_md)
    write_text(refs / "source.py", parsed["code"])
    write_yaml(refs / "analysis.yaml", analysis)
    data["artifacts"] = [
        {"path": "SKILL.md", "kind": "skill_md"},
        {"path": "references/source.py", "kind": "source"},
        {"path": "references/analysis.yaml", "kind": "analysis"},
    ]
    data["requirements"] = {"python_imports": analysis.get("imports", [])}
    data["reproducibility"] = {
        "entrypoint": "references/source.py",
        "required_inputs": analysis.get("data_inputs", []),
        "expected_outputs": [str(m.get("name", "")) for m in analysis.get("metrics", [])],
    }
    return True


def create_skill_candidate(
    root: Path,
    version: str,
    name: str,
    source_type: str,
    source_evidence: list[str],
    replace: bool = False,
) -> SkillVersion:
    require_memory_repo(root)
    candidate_dir = root / "skill_versions/.candidates" / version
    if candidate_dir.exists():
        if not replace:
            raise SkillVersionAlreadyExists(
                f"SkillVersion candidate already exists: {version} "
                "(pass replace=True to archive the old candidate and rebuild)"
            )
        archive_dir = root / "skill_versions/.archive/candidates" / f"{version}_{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}"
        archive_dir.parent.mkdir(parents=True, exist_ok=True)
        move(str(candidate_dir), str(archive_dir))
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
    if _enrich_candidate_from_source(candidate_dir, root, data, version, name, source_type, source_evidence):
        candidate = SkillVersion(**data)
        write_yaml(candidate_dir / "skill.yaml", candidate.model_dump(exclude_none=True))
        write_text(candidate_dir / "reproduce.md", _reproduce_reference(name))
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
        raise SkillVersionAlreadyExists(
            f"Approved SkillVersion already exists: {version}. "
            "Approved versions are immutable; create a new version instead of replacing."
        )
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
    if (directory / "SKILL.md").exists():
        files["SKILL.md"] = read_text(directory / "SKILL.md")
    references = directory / "references"
    if references.exists():
        for ref_path in sorted(references.rglob("*")):
            if ref_path.is_file():
                files[str(ref_path.relative_to(directory))] = read_text(ref_path)
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
