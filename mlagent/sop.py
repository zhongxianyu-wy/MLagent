"""Layer 3: skill_library — versioned SOP-skills with a strict gate.

Each SOP version is a Claude-Code skill (SKILL.md + scripts/) that is also a
strict, deterministic retraining recipe. Promotion requires:
  1. gate.tests_passed = True (the reproduction test ran clean)
  2. human_review.reviewed = True (a human confirmed performance + reproducibility)
Approved versions are immutable (supersession, never overwrite).
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from shutil import copytree
from typing import Any

from mlagent.errors import MlagentError
from mlagent.io import read_yaml, write_text, write_yaml
from mlagent.repo import require_memory_repo
from mlagent.schemas import Gate, SkillVersion


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- candidate creation ---


def create_candidate(
    root: Path,
    sop_name: str,
    version: str,
    source_type: str,
    source_evidence: list[str],
    background: str = "",
    reason: str = "",
    key_params: dict[str, Any] | None = None,
    key_optimizations: list[str] | None = None,
    test_command: str = "",
    replace: bool = False,
) -> SkillVersion:
    """Create a pending SOP candidate with a gate (tests_passed=False by default)."""
    require_memory_repo(root)
    cand_dir = root / "skill_library" / ".candidates" / sop_name / version
    if cand_dir.exists() and not replace:
        raise MlagentError(f"Candidate already exists: {sop_name}/{version} (pass replace=True)")
    cand_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "version": version,
        "name": sop_name,
        "object_type": "skill_version",
        "state": "pending_review",
        "source_type": source_type,
        "source_evidence": source_evidence,
        "artifacts": [],
        "requirements": {},
        "human_review": {"reviewed": False},
        "performance": {"primary_metric": {"name": "", "value": 0.0}},
        "reproducibility": {"entrypoint": "", "required_inputs": [], "expected_outputs": []},
        "background": background,
        "reason": reason,
        "key_params": key_params or {},
        "key_optimizations": key_optimizations or [],
        "gate": {"tests_passed": False, "test_command": test_command, "test_log": ""},
        "valid_from": None,
        "superseded_by": None,
    }
    sv = SkillVersion(**data)
    write_yaml(cand_dir / "sop.yaml", sv.model_dump(exclude_none=True))
    write_text(cand_dir / "SKILL.md", f"# Skill: {sop_name} ({version})\n\n> Pending review. Fill in reproduce steps + constraints.\n")
    (cand_dir / "scripts").mkdir(exist_ok=True)
    return sv


# --- gate result ---


def set_gate_result(root: Path, sop_name: str, version: str, tests_passed: bool, test_log: str = "") -> None:
    """Record the reproduction test result (called by the skill after running the test)."""
    require_memory_repo(root)
    cand = root / "skill_library" / ".candidates" / sop_name / version / "sop.yaml"
    if not cand.exists():
        raise MlagentError(f"Candidate not found: {sop_name}/{version}")
    data = read_yaml(cand)
    data["gate"] = {"tests_passed": tests_passed, "test_command": data.get("gate", {}).get("test_command", ""), "test_log": test_log}
    write_yaml(cand, data)


# --- approval (strict gate) ---


def approve_sop(
    root: Path,
    sop_name: str,
    version: str,
    reviewer: str,
    approval_note: str,
    performance: dict[str, Any],
) -> SkillVersion:
    """Promote a candidate to an approved, immutable SOP version. Requires gate.tests_passed=True."""
    require_memory_repo(root)
    cand_dir = root / "skill_library" / ".candidates" / sop_name / version
    approved_dir = root / "skill_library" / sop_name / version
    if not (cand_dir / "sop.yaml").exists():
        raise MlagentError(f"Candidate not found: {sop_name}/{version}")
    if approved_dir.exists():
        raise MlagentError(f"Approved version already exists (immutable): {sop_name}/{version}")

    data = read_yaml(cand_dir / "sop.yaml")
    gate = data.get("gate") or {}
    if not gate.get("tests_passed"):
        raise MlagentError(
            f"Gate not passed for {sop_name}/{version}: reproduction test must pass before approval. "
            "Run `mlagent set-gate-result --tests-passed` after the test succeeds."
        )

    ts = _now()
    data["state"] = "approved"
    data["human_review"] = {"reviewed": True, "reviewer": reviewer, "reviewed_at": ts, "approval_note": approval_note}
    data["performance"] = performance
    data["valid_from"] = ts
    approved = SkillVersion(**data)

    copytree(cand_dir, approved_dir)
    write_yaml(approved_dir / "sop.yaml", approved.model_dump(exclude_none=True))
    write_yaml(approved_dir / "performance.yaml", performance)

    # update global registry
    reg_path = root / "skill_library" / "registry.yaml"
    registry = read_yaml(reg_path)
    versions = [v for v in registry.get("versions", []) if not (v.get("name") == sop_name and v.get("version") == version)]
    versions.append({
        "name": sop_name,
        "version": version,
        "state": "approved",
        "reviewer": reviewer,
        "reviewed_at": ts,
        "primary_metric": performance.get("primary_metric", {}),
    })
    write_yaml(reg_path, {"versions": versions})
    return approved


# --- query ---


def list_sops(root: Path) -> list[dict[str, Any]]:
    """List approved SOPs from registry + pending candidates."""
    require_memory_repo(root)
    registry = read_yaml(root / "skill_library" / "registry.yaml")
    approved = list(registry.get("versions", []))
    candidates = []
    cand_root = root / "skill_library" / ".candidates"
    if cand_root.exists():
        for sop_dir in sorted(cand_root.iterdir()):
            if not sop_dir.is_dir():
                continue
            for ver_dir in sorted(sop_dir.iterdir()):
                sop_yaml = ver_dir / "sop.yaml"
                if sop_yaml.exists():
                    sd = read_yaml(sop_yaml)
                    # skip if this version is also approved (already in registry)
                    if not any(v.get("name") == sd.get("name") and v.get("version") == sd.get("version") for v in approved):
                        candidates.append({"name": sd.get("name"), "version": sd.get("version"), "state": sd.get("state")})
    return {"approved": approved, "candidates": candidates}


def get_sop(root: Path, sop_name: str, version: str, include_draft: bool = False) -> dict[str, Any]:
    """Read a SOP version bundle (approved dir, or candidate with --include-draft)."""
    require_memory_repo(root)
    approved = root / "skill_library" / sop_name / version
    candidate = root / "skill_library" / ".candidates" / sop_name / version
    if (approved / "sop.yaml").exists():
        source = "approved"
        directory = approved
    elif (candidate / "sop.yaml").exists():
        if not include_draft:
            raise MlagentError(f"{sop_name}/{version} is a pending candidate, not approved. Pass --include-draft.")
        source = "candidate"
        directory = candidate
    else:
        raise MlagentError(f"SOP version not found: {sop_name}/{version}")
    sop = read_yaml(directory / "sop.yaml")
    files: dict[str, str] = {}
    for fname in ("SKILL.md", "sop.yaml", "performance.yaml"):
        p = directory / fname
        if p.exists():
            files[fname] = p.read_text(encoding="utf-8")
    return {"name": sop_name, "version": version, "source": source, "state": sop.get("state"), "sop": sop, "files": files}
