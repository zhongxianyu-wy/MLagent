from __future__ import annotations

import json
from pathlib import Path

from src.models import SkillCandidate
from src.skill_bridge.candidate import SkillCandidateStore


class SkillCandidateGenerator:
    def __init__(
        self,
        candidate_store: SkillCandidateStore,
        output_root: str = "experiments/outputs/skill_candidates",
        id_factory=None,
        clock=None,
    ) -> None:
        self.candidate_store = candidate_store
        self.output_root = Path(output_root)
        self.id_factory = id_factory or (lambda: "candidate")
        self.clock = clock or (lambda: 0)

    def from_notebook(self, path: str) -> SkillCandidate:
        notebook = json.loads(Path(path).read_text())
        title = self._notebook_title(notebook) or "notebook-skill"
        body = self._notebook_skill_body(notebook)
        return self._create_candidate(
            source_type="notebook",
            source_ref=path,
            skill_name=title.lower().replace(" ", "-"),
            body=body,
        )

    def from_best_run(self, experiment_id: str, trace_summary: dict) -> SkillCandidate:
        return self._create_candidate(
            source_type="best_run",
            source_ref=experiment_id,
            skill_name=f"{experiment_id}-best-run",
            body=json.dumps(trace_summary, sort_keys=True),
        )

    def validate_structure(self, candidate_id: str) -> SkillCandidate:
        candidate = self.candidate_store.get(candidate_id)
        text = Path(candidate.draft_path).read_text()
        status = "passed" if text.startswith("---\nname:") else "failed"
        return self.candidate_store.update(
            candidate_id,
            validation_status=status,
            updated_at=self.clock(),
        )

    def _create_candidate(
        self, source_type: str, source_ref: str, skill_name: str, body: str
    ) -> SkillCandidate:
        candidate_id = self.id_factory()
        draft_dir = self.output_root / candidate_id
        draft_dir.mkdir(parents=True, exist_ok=True)
        draft_path = draft_dir / "SKILL.md"
        draft_path.write_text(
            f"---\nname: {skill_name}\ndescription: Draft SkillCandidate\n---\n\n{body}\n"
        )
        now = self.clock()
        return self.candidate_store.save(
            SkillCandidate(
                candidate_id=candidate_id,
                source_type=source_type,
                source_ref=source_ref,
                skill_name=skill_name,
                draft_path=str(draft_path),
                validation_status="pending",
                darwin_iteration_status="not_started",
                review_status="pending",
                approved_skill_id=None,
                created_at=now,
                updated_at=now,
            )
        )

    def _notebook_title(self, notebook: dict) -> str | None:
        for cell in notebook.get("cells", []):
            if cell.get("cell_type") == "markdown":
                source = "".join(cell.get("source", []))
                for line in source.splitlines():
                    if line.startswith("# "):
                        return line.removeprefix("# ").strip()
        return None

    def _notebook_skill_body(self, notebook: dict) -> str:
        markdown = []
        code = []
        for cell in notebook.get("cells", []):
            source = "".join(cell.get("source", []))
            if cell.get("cell_type") == "markdown":
                markdown.append(source)
            elif cell.get("cell_type") == "code":
                code.append(source)
        method_summary = "\n\n".join(markdown).strip()
        code_summary = "\n".join(code).strip()
        return "\n".join(
            [
                "## Inputs",
                "",
                "- Standardized NGS feature matrix with sample IDs.",
                "- Binary sample labels with declared positive and negative classes.",
                "",
                "## Procedure",
                "",
                method_summary,
                "",
                "```python",
                code_summary,
                "```",
                "",
                "## Evaluation",
                "",
                "- Use k-fold validation on the training set.",
                "- Select thresholds from concatenated validation-fold predictions.",
                "- Report held-out test metrics only after training-fold selection.",
                "",
                "## Review Status",
                "",
                "Pending human approval before publishing.",
            ]
        )
