from __future__ import annotations

from pathlib import Path
import shutil

from src.models import ApprovedSkill


class SkillRegistry:
    def __init__(self, root: str = ".claude/skills") -> None:
        self.root = Path(root)

    def list_skills(self) -> list[ApprovedSkill]:
        skills = []
        for skill_path in sorted(self.root.glob("*/SKILL.md")):
            meta = self._read_frontmatter(skill_path)
            skills.append(
                ApprovedSkill(
                    skill_id=skill_path.parent.name,
                    name=meta["name"],
                    path=str(skill_path),
                    description=meta.get("description", ""),
                    applicability="fixture",
                    version=meta.get("version", ""),
                    created_from_candidate_id=None,
                    last_used_at=None,
                )
            )
        return skills

    def get_metadata(self, skill_id: str) -> dict:
        return self._read_frontmatter(self.root / skill_id / "SKILL.md")

    def _read_frontmatter(self, path: Path) -> dict:
        lines = path.read_text().splitlines()
        if not lines or lines[0] != "---":
            raise ValueError("SKILL.md must start with frontmatter")
        meta: dict[str, object] = {}
        current_list_key = None
        for line in lines[1:]:
            if line == "---":
                break
            if line.startswith("  - ") and current_list_key:
                meta[current_list_key].append(line.removeprefix("  - ").strip())
                continue
            current_list_key = None
            if ":" not in line:
                continue
            key, value = line.split(":", 1)
            key = key.strip()
            value = value.strip()
            if value == "":
                meta[key] = []
                current_list_key = key
            else:
                meta[key] = value
        return meta

    def record_use(self, skill_id: str, used_at: int) -> None:
        # File-backed fixture registry has no persistent usage index yet.
        return None


class SkillPublisher:
    def __init__(self, candidate_store, skills_root: str = ".claude/skills") -> None:
        self.candidate_store = candidate_store
        self.skills_root = Path(skills_root)

    def publish(self, candidate_id: str, approved: bool) -> ApprovedSkill:
        if not approved:
            raise ValueError("human approval is required before publishing")
        candidate = self.candidate_store.get(candidate_id)
        target_dir = self.skills_root / candidate.skill_name
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / "SKILL.md"
        shutil.copyfile(candidate.draft_path, target_path)
        updated = self.candidate_store.update(
            candidate_id,
            review_status="approved",
            approved_skill_id=candidate.skill_name,
            updated_at=candidate.updated_at,
        )
        return ApprovedSkill(
            skill_id=updated.approved_skill_id,
            name=updated.skill_name,
            path=str(target_path),
            description="Published SkillCandidate",
            applicability="approved",
            version="1.0.0",
            created_from_candidate_id=updated.candidate_id,
            last_used_at=None,
        )
