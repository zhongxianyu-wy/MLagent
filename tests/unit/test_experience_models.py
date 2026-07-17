from dataclasses import FrozenInstanceError
from pathlib import Path

import pytest

from src.domain.models import (
    CompleteSessionCommand,
    ExperienceCitation,
    ExperienceContent,
    ExperienceEvidence,
    ExperienceSearchResult,
    ExperienceSnapshot,
    ReviewExperienceCommand,
    SessionExperienceOutcome,
)


def content(**updates) -> ExperienceContent:
    values = {
        "conclusion": "Feature filtering improved roc_auc.",
        "applicability": "Same assay and label definition.",
        "recommended_action": "Retest feature filtering.",
        "failure_boundary": "Observed on one frozen split.",
        "risk": "The effect may not transfer.",
        "confidence": 0.6,
    }
    values.update(updates)
    return ExperienceContent(**values)


def evidence() -> tuple[ExperienceEvidence, ...]:
    return tuple(
        ExperienceEvidence(
            role=role,
            asset_id=f"{role}-1",
            asset_path=f"evidence/{role}-1.json",
            sha256=character * 64,
        )
        for role, character in zip(
            ("dataset", "run", "training_instance", "raw_record"),
            "abcd",
        )
    )


def snapshot(**updates) -> ExperienceSnapshot:
    values = {
        "asset_id": "experience-1",
        "asset_path": "experiences/experience-1/event-1.json",
        "event_id": "event-1",
        "event_fingerprint": "e" * 64,
        "previous_event_id": None,
        "previous_event_fingerprint": None,
        "state": "pending",
        "content": content(),
        "evidence": evidence(),
        "extraction_session_id": "session-1",
        "source_kind": "metric_improvement",
        "relation_type": None,
        "related_experience_id": None,
        "created_at": "2026-07-17T00:00:00Z",
        "created_by": "agent",
        "reviewed_at": None,
        "reviewed_by": None,
        "decision": None,
    }
    values.update(updates)
    return ExperienceSnapshot(**values)


@pytest.mark.parametrize(
    "field_name",
    (
        "conclusion",
        "applicability",
        "recommended_action",
        "failure_boundary",
        "risk",
    ),
)
def test_experience_content_requires_bounded_nonempty_fields(field_name):
    with pytest.raises(ValueError, match=field_name):
        content(**{field_name: ""})


@pytest.mark.parametrize("confidence", (-0.01, 1.01, float("nan"), True))
def test_experience_content_requires_finite_confidence(confidence):
    with pytest.raises(ValueError, match="confidence"):
        content(confidence=confidence)


def test_pending_experience_requires_all_direct_evidence_roles():
    with pytest.raises(ValueError, match="evidence roles"):
        snapshot(evidence=evidence()[:-1])


def test_experience_evidence_requires_sha256():
    with pytest.raises(ValueError, match="sha256"):
        ExperienceEvidence(
            role="dataset",
            asset_id="dataset-1",
            asset_path="datasets/dataset-1/v0001/manifest.json",
            sha256="not-a-hash",
        )


def test_relation_fields_are_paired_and_state_specific():
    with pytest.raises(ValueError, match="relation"):
        snapshot(relation_type="conflicts_with")
    with pytest.raises(ValueError, match="relation"):
        snapshot(
            state="pending",
            relation_type="conflicts_with",
            related_experience_id="experience-2",
        )


def test_reviewed_state_requires_audit_fields():
    with pytest.raises(ValueError, match="reviewed_at"):
        snapshot(
            state="trusted",
            previous_event_id="event-0",
            previous_event_fingerprint="d" * 64,
        )


def test_event_fingerprint_must_chain_with_previous_event():
    with pytest.raises(ValueError, match="previous_event_fingerprint"):
        snapshot(
            state="trusted",
            previous_event_id="event-0",
            reviewed_at="2026-07-17T00:01:00Z",
            reviewed_by="reviewer",
            decision="approve",
        )


def test_review_command_rejects_empty_reviewer_content():
    with pytest.raises(ValueError, match="conclusion"):
        ReviewExperienceCommand(
            connection_path=Path(".mlagent-workspace.json"),
            experience_id="experience-1",
            decision="approve",
            content=content(conclusion=""),
        )


def test_commands_and_results_are_immutable_and_json_safe():
    command = CompleteSessionCommand(
        connection_path=Path(".mlagent-workspace.json"),
        session_id="session-1",
    )
    citation = ExperienceCitation(
        experience_id="experience-1",
        event_id="event-2",
        state="trusted",
        why_applicable="Same dataset and metric.",
    )
    result = ExperienceSearchResult(
        experience=snapshot(
            state="trusted",
            previous_event_id="event-1",
            previous_event_fingerprint="d" * 64,
            reviewed_at="2026-07-17T00:01:00Z",
            reviewed_by="reviewer",
            decision="approve",
        ),
        why_applicable="Same dataset and metric.",
        score=4,
    )
    outcome = SessionExperienceOutcome(
        session_id="session-1",
        outcome="created",
        candidate_ids=("experience-1",),
        new_event_ids=("run-event-2",),
        new_instance_ids=("instance-2",),
        pending_review_count=1,
        sync=None,
    )

    assert command.to_dict()["connection_path"] == ".mlagent-workspace.json"
    assert citation.to_dict()["state"] == "trusted"
    assert result.to_dict()["experience"]["state"] == "trusted"
    assert outcome.to_dict()["candidate_ids"] == ["experience-1"]
    with pytest.raises(FrozenInstanceError):
        citation.state = "pending"


@pytest.mark.parametrize("state", ("rejected", "conflict", "superseded"))
def test_citation_rejects_inactive_experience_states(state):
    with pytest.raises(ValueError, match="state"):
        ExperienceCitation(
            experience_id="experience-1",
            event_id="event-2",
            state=state,
            why_applicable="Same dataset.",
        )
