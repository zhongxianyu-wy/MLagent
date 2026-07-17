import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

from src.domain.core import DomainCore
from src.domain.models import (
    ApproveExplorationPlanCommand,
    BootstrapMemoryCommand,
    ConfirmDatasetCommand,
    ExecuteExplorationCommand,
    ExperienceContent,
    ExplorationRound,
    RecordExplorationPlanCommand,
    ReviewExperienceCommand,
    WorkspaceError,
)


@pytest.fixture
def domain_experience_workspace(tmp_path):
    core = DomainCore(
        id_factory=lambda: "tmr-experience",
        dataset_id_factory=lambda: "ds-1",
        exploration_event_id_factory=lambda: "plan-event-1",
        exploration_approval_id_factory=lambda: "plan-approval-1",
        clock=lambda: "2026-07-17T01:00:00Z",
    )
    connection = tmp_path / ".mlagent-workspace.json"
    memory_root = tmp_path / "team-memory"
    core.bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=memory_root,
            actor_id="alice",
            connection_path=connection,
        )
    )
    sample_ids = [f"s{index:02d}" for index in range(12)]
    features = tmp_path / "features.csv"
    labels = tmp_path / "labels.csv"
    pd.DataFrame(
        {
            "sample_id": sample_ids,
            "f1": [index / 10 for index in range(12)],
        }
    ).to_csv(features, index=False)
    pd.DataFrame(
        {
            "sample_id": sample_ids,
            "group": ["case"] * 6 + ["control"] * 6,
        }
    ).to_csv(labels, index=False)
    core.confirm_dataset(
        ConfirmDatasetCommand(
            connection_path=connection,
            feature_path=features,
            label_path=labels,
            sample_id_col="sample_id",
            label_col="group",
            task_type="binary",
            primary_metric="roc_auc",
            split_strategy="train_only",
            target_metric=0.9,
            positive_class="case",
        )
    )
    code_root = tmp_path / "code"
    code_root.mkdir()
    (code_root / "train.py").write_text(
        "print('train')\n",
        encoding="utf-8",
    )
    return DomainExperienceWorkspace(
        core,
        connection,
        memory_root,
        code_root,
    )


class DomainExperienceWorkspace:
    def __init__(self, core, connection, memory_root, code_root):
        self.core = core
        self.connection = connection
        self.memory_root = memory_root
        self.code_root = code_root

    def seed_experience(self, experience_id, state):
        dataset_path = next(
            self.memory_root.glob("datasets/ds-1/v0001/manifest.json")
        )
        dataset_asset_id = json.loads(
            dataset_path.read_text(encoding="utf-8")
        )["asset_id"]
        evidence_specs = [
            ("dataset", dataset_asset_id, dataset_path),
            (
                "run",
                f"run-{experience_id}",
                self.memory_root
                / f"raw-records/runs/evidence/{experience_id}-run.json",
            ),
            (
                "training_instance",
                f"instance-{experience_id}",
                self.memory_root
                / f"runs/evidence/instances/{experience_id}/manifest.json",
            ),
            (
                "raw_record",
                f"record-{experience_id}",
                self.memory_root
                / f"raw-records/runs/evidence/{experience_id}-record.json",
            ),
        ]
        for role, asset_id, path in evidence_specs[1:]:
            if role == "run":
                payload = {
                    "asset_type": "run_event",
                    "asset_id": f"event-start-{experience_id}",
                    "run_id": asset_id,
                    "event_type": "run_started",
                    "created_at": "2026-07-17T00:00:00Z",
                }
            elif role == "raw_record":
                payload = {
                    "asset_type": "run_event",
                    "asset_id": asset_id,
                    "run_id": f"run-{experience_id}",
                    "event_type": "instance_completed",
                    "created_at": "2026-07-17T00:00:00Z",
                }
            else:
                payload = {
                    "asset_type": role,
                    "asset_id": asset_id,
                    "created_at": "2026-07-17T00:00:00Z",
                }
            write_json(
                path,
                payload,
            )
        evidence = [
            {
                "role": role,
                "asset_id": asset_id,
                "asset_path": path.relative_to(self.memory_root).as_posix(),
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
            for role, asset_id, path in evidence_specs
        ]
        family = self.memory_root / "experiences" / experience_id
        pending_event = f"{experience_id}-pending"
        content = {
            "conclusion": "Feature filtering improved roc_auc.",
            "applicability": "Same dataset and label definition.",
            "recommended_action": "Retest feature filtering.",
            "failure_boundary": "One frozen split.",
            "risk": "May not transfer.",
            "confidence": 0.6,
        }
        pending_payload = {
                "asset_type": "experience_event",
                "asset_id": pending_event,
                "experience_id": experience_id,
                "schema_version": 1,
                "previous_event_id": None,
                "previous_event_fingerprint": None,
                "state": "pending",
                "content": content,
                "evidence": evidence,
                "extraction_session_id": "session-seed",
                "source_kind": "metric_improvement",
                "relation_type": None,
                "related_experience_id": None,
                "created_at": "2026-07-17T00:00:00Z",
                "created_by": "agent",
                "reviewed_at": None,
                "reviewed_by": None,
                "decision": None,
            }
        write_experience_event(
            family / f"{pending_event}.json",
            pending_payload,
        )
        if state == "pending":
            return pending_event
        trusted_event = f"{experience_id}-trusted"
        trusted_content = dict(content, confidence=0.9)
        trusted_payload = {
                "asset_type": "experience_event",
                "asset_id": trusted_event,
                "experience_id": experience_id,
                "schema_version": 1,
                "previous_event_id": pending_event,
                "previous_event_fingerprint": pending_payload[
                    "event_fingerprint"
                ],
                "state": "trusted",
                "content": trusted_content,
                "evidence": evidence,
                "extraction_session_id": "session-seed",
                "source_kind": "metric_improvement",
                "relation_type": None,
                "related_experience_id": None,
                "created_at": "2026-07-17T00:01:00Z",
                "created_by": "reviewer",
                "reviewed_at": "2026-07-17T00:01:00Z",
                "reviewed_by": "reviewer",
                "decision": "approve",
            }
        write_experience_event(
            family / f"{trusted_event}.json",
            trusted_payload,
        )
        return trusted_event

    def plan_command(self, **overrides):
        values = {
            "connection_path": self.connection,
            "code_root": self.code_root,
            "dataset_id": "ds-1",
            "dataset_version": 1,
            "plan_id": "plan-1",
            "planning_session_id": "session-plan",
            "user_direction": "Improve validation AUC",
            "baseline_hypothesis": "Fit a baseline",
            "rounds": (
                ExplorationRound(
                    1,
                    "Baseline is stable",
                    "baseline",
                    ("fit baseline",),
                ),
            ),
            "stop_conditions": ("target reached",),
            "risks": ("validation overfit",),
            "resource_limits": {"max_minutes": 10},
            "candidate_code_paths": ("train.py",),
        }
        values.update(overrides)
        return RecordExplorationPlanCommand(**values)


def test_domain_core_searches_trusted_and_optional_pending_separately(
    domain_experience_workspace,
):
    workspace = domain_experience_workspace
    workspace.seed_experience("experience-trusted", "trusted")
    workspace.seed_experience("experience-pending", "pending")

    trusted, pending = workspace.core.search_experiences(
        workspace.connection,
        query="feature filtering roc_auc",
        dataset_id="ds-1",
        include_pending=True,
    )

    assert [item.experience.state for item in trusted] == ["trusted"]
    assert [item.experience.state for item in pending] == ["pending"]
    assert all(item.why_applicable for item in (*trusted, *pending))


def test_domain_core_resolves_exact_experience_versions_and_excludes_pending(
    domain_experience_workspace,
):
    workspace = domain_experience_workspace
    trusted_event = workspace.seed_experience(
        "experience-trusted",
        "trusted",
    )
    pending_event = workspace.seed_experience(
        "experience-pending",
        "pending",
    )
    workspace.seed_experience("experience-excluded", "pending")

    plan = workspace.core.record_exploration_plan(
        workspace.plan_command(
            trusted_experience_ids=("experience-trusted",),
            pending_experience_ids=(
                "experience-pending",
                "experience-excluded",
            ),
            excluded_pending_experience_ids=("experience-excluded",),
            experience_applicability={
                "experience-trusted": "Same Dataset and metric.",
                "experience-pending": "Matching optimization direction.",
            },
        )
    )

    assert tuple(item.event_id for item in plan.experience_citations) == (
        trusted_event,
        pending_event,
    )
    assert all(
        item.experience_id != "experience-excluded"
        for item in plan.experience_citations
    )


@pytest.mark.parametrize(
    "overrides",
    (
        {
            "trusted_experience_ids": ("experience-pending",),
            "experience_applicability": {
                "experience-pending": "Claimed as trusted."
            },
        },
        {
            "pending_experience_ids": ("experience-pending",),
            "experience_applicability": {},
        },
        {
            "trusted_experience_ids": ("experience-missing",),
            "experience_applicability": {
                "experience-missing": "Missing evidence."
            },
        },
    ),
)
def test_domain_core_rejects_misclassified_unexplained_or_missing_experience(
    domain_experience_workspace,
    overrides,
):
    workspace = domain_experience_workspace
    workspace.seed_experience("experience-pending", "pending")

    with pytest.raises(WorkspaceError):
        workspace.core.record_exploration_plan(
            workspace.plan_command(**overrides)
        )


def test_review_after_plan_record_makes_experience_citation_stale(
    domain_experience_workspace,
):
    workspace = domain_experience_workspace
    workspace.seed_experience("experience-pending", "pending")
    plan = workspace.core.record_exploration_plan(
        workspace.plan_command(
            pending_experience_ids=("experience-pending",),
            experience_applicability={
                "experience-pending": "Matching optimization direction."
            },
        )
    )
    pending = workspace.core.list_experiences(
        workspace.connection,
        states=("pending",),
    )[0]
    workspace.core.review_experience(
        ReviewExperienceCommand(
            workspace.connection,
            pending.asset_id,
            "approve",
            ExperienceContent(
                conclusion=pending.content.conclusion,
                applicability=pending.content.applicability,
                recommended_action=pending.content.recommended_action,
                failure_boundary=pending.content.failure_boundary,
                risk=pending.content.risk,
                confidence=0.9,
            ),
        )
    )

    with pytest.raises(WorkspaceError) as caught:
        workspace.core.approve_exploration_plan(
            ApproveExplorationPlanCommand(
                workspace.connection,
                workspace.code_root,
                plan.plan_id,
            )
        )

    assert caught.value.code == "experience_reference_stale"


def test_actual_training_result_writes_back_only_included_experience_versions(
    domain_experience_workspace,
):
    workspace = domain_experience_workspace
    workspace.seed_experience("experience-trusted", "trusted")
    workspace.seed_experience("experience-pending", "pending")
    workspace.seed_experience("experience-excluded", "pending")
    (workspace.code_root / "train.py").write_text(
        "from sklearn.linear_model import LogisticRegression\n\n"
        "def build_estimator(context):\n"
        "    return LogisticRegression(\n"
        "        random_state=context['random_seed'], max_iter=200)\n",
        encoding="utf-8",
    )
    plan = workspace.core.record_exploration_plan(
        workspace.plan_command(
            trusted_experience_ids=("experience-trusted",),
            pending_experience_ids=(
                "experience-pending",
                "experience-excluded",
            ),
            excluded_pending_experience_ids=("experience-excluded",),
            experience_applicability={
                "experience-trusted": "Same Dataset and metric.",
                "experience-pending": "Matching optimization direction.",
            },
        )
    )
    approval = workspace.core.approve_exploration_plan(
        ApproveExplorationPlanCommand(
            workspace.connection,
            workspace.code_root,
            plan.plan_id,
        )
    )

    status = workspace.core.execute_exploration(
        ExecuteExplorationCommand(
            connection_path=workspace.connection,
            code_root=workspace.code_root,
            dataset_id="ds-1",
            dataset_version=1,
            plan_id=plan.plan_id,
            approval_id=approval.asset_id,
            entrypoint_path="train.py",
        )
    )

    start = next(
        json.loads(path.read_text(encoding="utf-8"))
        for path in (
            workspace.memory_root
            / "raw-records/runs"
            / status.run_id
        ).glob("*.json")
        if json.loads(path.read_text(encoding="utf-8"))["event_type"]
        == "run_started"
    )
    manifest = json.loads(
        next(
            (
                workspace.memory_root
                / "runs"
                / status.run_id
                / "instances"
            ).glob("*/manifest.json")
        ).read_text(encoding="utf-8")
    )
    expected_ids = ["experience-trusted", "experience-pending"]
    assert [
        item["experience_id"] for item in start["experience_citations"]
    ] == expected_ids
    assert [
        item["experience_id"]
        for item in manifest["experience_citations"]
    ] == expected_ids
    assert "experience-excluded" not in json.dumps(manifest)


def write_json(path, payload):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def write_experience_event(path, payload):
    payload["event_fingerprint"] = hashlib.sha256(
        json.dumps(
            payload,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    write_json(path, payload)
