from __future__ import annotations

from src.data_intake.explorer import IntakeInspection, inspect_path
from src.data_intake.manifest import build_manifest_from_inspection
from src.data_intake.socratic import SocraticIntakeState
from src.models import DatasetManifest


class DatasetService:
    def __init__(self, output_root: str = "experiments/standardized") -> None:
        self.output_root = output_root
        self.state = SocraticIntakeState()

    def inspect_path(self, path: str) -> IntakeInspection:
        return self.state.save(inspect_path(path))

    def answer_clarification(self, session_id: str, answer: str) -> IntakeInspection:
        return self.state.answer(session_id, answer)

    def build_manifest(
        self,
        session_id: str,
        split_strategy: str = "train_only",
        split_ratio: float | None = None,
        random_seed: int | None = None,
    ) -> DatasetManifest:
        inspection = self.state.get(session_id)
        return build_manifest_from_inspection(
            inspection,
            self.output_root,
            split_strategy=split_strategy,
            split_ratio=split_ratio,
            random_seed=random_seed,
        )
