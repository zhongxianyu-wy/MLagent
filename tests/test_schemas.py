import math

import pytest
from pydantic import ValidationError

from mlagent.schemas import (
    Conclusion,
    ExperienceRecord,
    Gate,
    Performance,
    RawMemoryRecord,
    SkillVersion,
)


def test_raw_memory_with_conclusion():
    rec = RawMemoryRecord(
        id="raw_001",
        type="run",
        created_at="2026-07-03T10:00:00+08:00",
        goal="Improve AUC",
        conclusion=Conclusion(hypothesis="top-50 features help", outcome="confirmed", summary="auc +0.03"),
    )
    assert rec.conclusion.outcome == "confirmed"
    assert rec.type == "run"


def test_raw_memory_rejects_unknown_type():
    with pytest.raises(ValidationError):
        RawMemoryRecord(id="r", type="bogus", created_at="2026-07-03T10:00:00+08:00")


def test_experience_supports_convention_type_and_defaults():
    exp = ExperienceRecord(
        id="exp_001",
        type="convention",
        summary="Use 10-fold StratifiedKFold",
        confidence="high",
        needs_review=False,
        source_raw_records=["raw_memory/runs/raw_001.yaml"],
        created_at="2026-07-03T10:30:00+08:00",
    )
    assert exp.object_type == "experience"
    assert exp.verified == "unverified"
    assert exp.maturity == "candidate"
    assert exp.derived_from == []
    assert exp.decision is None


def test_experience_rejects_bad_confidence():
    with pytest.raises(ValidationError):
        ExperienceRecord(
            id="e", type="lesson", summary="s", confidence="huge", needs_review=False, created_at="2026-07-03T10:00:00+08:00"
        )


def test_skill_version_rejects_unreviewed_approved():
    with pytest.raises(ValidationError):
        SkillVersion(
            version="v001",
            name="baseline",
            state="approved",
            source_type="best_run",
            human_review={"reviewed": False},
            performance={},
        )


def test_skill_version_approves_when_reviewed_and_carries_metadata():
    sv = SkillVersion(
        version="v001",
        name="baseline",
        state="approved",
        source_type="exploration",
        human_review={"reviewed": True, "reviewer": "human", "approval_note": "ok"},
        performance={"primary_metric": {"name": "auc", "value": 0.91}},
        background="early baseline",
        reason="first to hit target",
        key_params={"n_estimators": 500},
        key_optimizations=["chi-square top-50"],
        gate=Gate(tests_passed=True, test_command="python reproduce.py"),
    )
    assert sv.gate.tests_passed is True
    assert sv.key_optimizations == ["chi-square top-50"]


def test_performance_rejects_empty_and_nonfinite():
    with pytest.raises(ValidationError):
        Performance(primary_metric={"name": "", "value": 0.9}, dataset_version="d", validation_protocol="h")
    with pytest.raises(ValidationError):
        Performance(
            primary_metric={"name": "auc", "value": math.nan},
            dataset_version="d",
            validation_protocol="h",
        )
