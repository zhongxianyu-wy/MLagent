from __future__ import annotations

from dataclasses import replace

from src.data_intake.explorer import IntakeInspection


class SocraticIntakeState:
    def __init__(self) -> None:
        self._inspections: dict[str, IntakeInspection] = {}

    def save(self, inspection: IntakeInspection) -> IntakeInspection:
        self._inspections[inspection.session_id] = inspection
        return inspection

    def get(self, session_id: str) -> IntakeInspection:
        return self._inspections[session_id]

    def answer(self, session_id: str, answer: str) -> IntakeInspection:
        inspection = self.get(session_id)
        positive = "tumor" if "tumor" in answer else inspection.positive_label
        negative = "normal" if "normal" in answer else inspection.negative_label
        updated = replace(
            inspection,
            positive_label=positive,
            negative_label=negative,
            ready=True,
            unresolved_questions=[],
        )
        return self.save(updated)
