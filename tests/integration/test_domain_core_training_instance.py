import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pandas as pd
import pytest

from src.domain.core import DomainCore
from src.domain.models import (
    ApproveExplorationPlanCommand,
    BootstrapMemoryCommand,
    ConfirmDatasetCommand,
    ExecuteExplorationCommand,
    ExplorationRound,
    RecordExplorationPlanCommand,
    RecoverRunCommand,
    RequestRunStopCommand,
    WorkspaceError,
)


@pytest.fixture
def training_workspace(tmp_path):
    event_ids = iter(f"plan-event-{index}" for index in range(1, 5))
    approval_ids = iter(f"approval-{index}" for index in range(1, 5))
    core = DomainCore(
        id_factory=lambda: "tmr-1",
        dataset_id_factory=lambda: "ds-1",
        exploration_event_id_factory=lambda: next(event_ids),
        exploration_approval_id_factory=lambda: next(approval_ids),
    )
    connection_path = tmp_path / ".mlagent-workspace.json"
    memory_root = tmp_path / "team-memory"
    core.bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=memory_root,
            actor_id="alice",
            connection_path=connection_path,
        )
    )
    sample_ids = [f"s{index:02d}" for index in range(24)]
    labels = ["control"] * 12 + ["case"] * 12
    features = tmp_path / "features.csv"
    label_path = tmp_path / "labels.csv"
    pd.DataFrame(
        {
            "sample_id": sample_ids,
            "f1": [value - 12 for value in range(24)],
            "f2": [(value - 12) * 0.5 for value in range(24)],
        }
    ).to_csv(features, index=False)
    pd.DataFrame(
        {"sample_id": sample_ids, "group": labels}
    ).to_csv(label_path, index=False)
    core.confirm_dataset(
        ConfirmDatasetCommand(
            connection_path=connection_path,
            feature_path=features,
            label_path=label_path,
            sample_id_col="sample_id",
            label_col="group",
            task_type="binary",
            positive_class="case",
            primary_metric="roc_auc",
            split_strategy="train_only",
            target_metric=0.95,
            random_seed=42,
        )
    )
    code_root = tmp_path / "code"
    code_root.mkdir()
    (code_root / "estimator.py").write_text(
        "from sklearn.dummy import DummyClassifier\n"
        "from sklearn.linear_model import LogisticRegression\n"
        "from sklearn.pipeline import Pipeline\n"
        "from sklearn.preprocessing import StandardScaler\n\n"
        "def build_estimator(context):\n"
        "    if context['round_number'] == 1:\n"
        "        return DummyClassifier(strategy='prior')\n"
        "    return Pipeline([\n"
        "        ('scale', StandardScaler()),\n"
        "        ('model', LogisticRegression(\n"
        "            random_state=context['random_seed'], max_iter=500)),\n"
        "    ])\n",
        encoding="utf-8",
    )
    return TrainingWorkspace(core, connection_path, memory_root, code_root)


class TrainingWorkspace:
    def __init__(self, core, connection_path, memory_root, code_root):
        self.core = core
        self.connection_path = connection_path
        self.memory_root = memory_root
        self.code_root = code_root

    def record(self, resource_limits=None):
        return self.core.record_exploration_plan(
            RecordExplorationPlanCommand(
                connection_path=self.connection_path,
                code_root=self.code_root,
                dataset_id="ds-1",
                dataset_version=1,
                plan_id="plan-1",
                planning_session_id="session-1",
                user_direction="Improve validation AUC",
                baseline_hypothesis="Start with a weak controlled baseline",
                rounds=(
                    ExplorationRound(
                        round_number=1,
                        hypothesis="A prior-only baseline establishes reference performance",
                        optimization_direction="baseline",
                        intended_changes=("fit prior-only baseline",),
                    ),
                    ExplorationRound(
                        round_number=2,
                        hypothesis="Scaled linear separation improves AUC",
                        optimization_direction="model_selection",
                        intended_changes=("fit scaled logistic regression",),
                    ),
                ),
                stop_conditions=("target reached", "round budget exhausted"),
                risks=("validation overfitting",),
                resource_limits=(
                    resource_limits
                    or {"max_minutes": 1, "max_parallel_jobs": 1}
                ),
                candidate_code_paths=("estimator.py",),
            )
        )

    def approve(self):
        return self.core.approve_exploration_plan(
            ApproveExplorationPlanCommand(
                connection_path=self.connection_path,
                code_root=self.code_root,
                plan_id="plan-1",
            )
        )

    def command(self, approval_id, human_marked_rounds=()):
        return ExecuteExplorationCommand(
            connection_path=self.connection_path,
            code_root=self.code_root,
            dataset_id="ds-1",
            dataset_version=1,
            plan_id="plan-1",
            approval_id=approval_id,
            entrypoint_path="estimator.py",
            human_marked_rounds=human_marked_rounds,
        )


def test_approved_plan_executes_real_rounds_and_seals_lineage(training_workspace):
    training_workspace.record()
    approval = training_workspace.approve()

    status = training_workspace.core.execute_exploration(
        training_workspace.command(approval.asset_id)
    )

    assert status.state == "completed"
    assert status.stop_reason == "target_metric_reached"
    assert len(status.rounds) == 2
    assert status.rounds[0].model_retention_reasons == ("baseline",)
    assert status.rounds[1].model_retention_reasons == ("stage_best",)
    assert status.rounds[1].parent_instance_id == status.rounds[0].instance_id
    assert status.best_instance_id == status.rounds[1].instance_id
    assert status.best_primary_metric_value >= 0.95
    assert training_workspace.core.get_run_status(
        training_workspace.connection_path,
        status.run_id,
    ) == status
    assert training_workspace.core.list_run_statuses(
        training_workspace.connection_path
    ) == (status,)
    assert list((training_workspace.memory_root / "sops").iterdir()) == []
    assert list((training_workspace.memory_root / "models").iterdir()) == []


def test_recovery_resume_retries_with_frozen_code_and_new_instance(
    training_workspace,
):
    class SimulatedInterpreterExit:
        def execute(self, prepared, stop_requested, timeout_seconds):
            raise SystemExit("simulated interpreter exit")

    training_workspace.record()
    approval = training_workspace.approve()
    training_workspace.core.training_executor_factory = (
        lambda: SimulatedInterpreterExit()
    )

    with pytest.raises(SystemExit):
        training_workspace.core.execute_exploration(
            training_workspace.command(approval.asset_id)
        )
    interrupted = training_workspace.core.list_run_statuses(
        training_workspace.connection_path
    )[0]
    assert interrupted.state == "recovery_required"
    (training_workspace.code_root / "estimator.py").write_text(
        "def build_estimator(context):\n    return object()\n",
        encoding="utf-8",
    )
    training_workspace.core.training_executor_factory = None

    recovered = training_workspace.core.recover_run(
        RecoverRunCommand(
            connection_path=training_workspace.connection_path,
            run_id=interrupted.run_id,
            action="resume",
        )
    )

    failed_attempts = [
        round_status
        for round_status in recovered.rounds
        if round_status.error_code == "interrupted"
    ]
    completed_attempts = [
        round_status
        for round_status in recovered.rounds
        if round_status.instance_state == "completed"
    ]
    assert recovered.state == "completed"
    assert len(failed_attempts) == 1
    assert len(completed_attempts) == 2
    assert failed_attempts[0].instance_id != completed_attempts[0].instance_id
    assert completed_attempts[1].parent_instance_id == completed_attempts[0].instance_id


def test_denied_execution_creates_no_run_or_training_instance(training_workspace):
    training_workspace.record()

    with pytest.raises(WorkspaceError) as caught:
        training_workspace.core.execute_exploration(
            training_workspace.command("missing-approval")
        )

    assert caught.value.code == "plan_approval_not_found"
    assert list((training_workspace.memory_root / "runs").iterdir()) == []
    assert list(
        (training_workspace.memory_root / "raw-records" / "runs").glob("**/*")
    ) == []


def test_workspace_code_edit_after_approval_blocks_before_run_start(
    training_workspace,
):
    training_workspace.record()
    approval = training_workspace.approve()
    (training_workspace.code_root / "estimator.py").write_text(
        "def build_estimator(context):\n    return object()\n",
        encoding="utf-8",
    )

    with pytest.raises(WorkspaceError) as caught:
        training_workspace.core.execute_exploration(
            training_workspace.command(approval.asset_id)
        )

    assert caught.value.code == "approval_stale"
    assert list((training_workspace.memory_root / "runs").iterdir()) == []


def test_stop_request_is_exposed_only_through_domain_core(training_workspace):
    training_workspace.record()
    approval = training_workspace.approve()
    status = training_workspace.core.execute_exploration(
        training_workspace.command(approval.asset_id)
    )

    with pytest.raises(WorkspaceError) as caught:
        training_workspace.core.request_run_stop(
            RequestRunStopCommand(
                connection_path=training_workspace.connection_path,
                run_id=status.run_id,
            )
        )

    assert caught.value.code == "run_already_finished"


def test_invalid_estimator_seals_failed_instance_without_model_claim(
    training_workspace,
):
    (training_workspace.code_root / "estimator.py").write_text(
        "def build_estimator(context):\n    return object()\n",
        encoding="utf-8",
    )
    training_workspace.record()
    approval = training_workspace.approve()

    status = training_workspace.core.execute_exploration(
        training_workspace.command(approval.asset_id)
    )

    assert status.state == "failed"
    assert len(status.rounds) == 1
    assert status.rounds[0].instance_state == "failed"
    assert status.rounds[0].error_code == "invalid_estimator"
    assert status.rounds[0].primary_metric_value is None
    assert status.rounds[0].model_retention_reasons == ()
    assert list((training_workspace.memory_root / "models").iterdir()) == []
    assert list((training_workspace.memory_root / "sops").iterdir()) == []


def test_approved_timeout_seals_timed_out_instance(training_workspace):
    (training_workspace.code_root / "estimator.py").write_text(
        "import time\n"
        "from sklearn.dummy import DummyClassifier\n"
        "def build_estimator(context):\n"
        "    time.sleep(2)\n"
        "    return DummyClassifier(strategy='prior')\n",
        encoding="utf-8",
    )
    training_workspace.record(resource_limits={"max_seconds": 0.01})
    approval = training_workspace.approve()

    status = training_workspace.core.execute_exploration(
        training_workspace.command(approval.asset_id)
    )

    assert status.state == "timed_out"
    assert status.rounds[0].instance_state == "timed_out"
    assert status.rounds[0].error_code == "training_timeout"


def test_live_stop_request_terminates_worker_and_seals_stopped_instance(
    training_workspace,
):
    (training_workspace.code_root / "estimator.py").write_text(
        "import time\n"
        "from sklearn.dummy import DummyClassifier\n"
        "def build_estimator(context):\n"
        "    time.sleep(5)\n"
        "    return DummyClassifier(strategy='prior')\n",
        encoding="utf-8",
    )
    training_workspace.record()
    approval = training_workspace.approve()

    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(
            training_workspace.core.execute_exploration,
            training_workspace.command(approval.asset_id),
        )
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            statuses = training_workspace.core.list_run_statuses(
                training_workspace.connection_path
            )
            if statuses and statuses[0].state == "running":
                break
            time.sleep(0.05)
        else:
            raise AssertionError("Run did not enter running state")
        requested = training_workspace.core.request_run_stop(
            RequestRunStopCommand(
                connection_path=training_workspace.connection_path,
                run_id=statuses[0].run_id,
                reason="user_stop",
            )
        )
        status = future.result(timeout=10)

    assert requested.stop_requested is True
    assert status.state == "stopped"
    assert status.rounds[0].instance_state == "stopped"
    assert status.rounds[0].error_code == "user_stop"


def test_human_mark_adds_retention_reason_without_creating_formal_model(
    training_workspace,
):
    training_workspace.record()
    approval = training_workspace.approve()

    status = training_workspace.core.execute_exploration(
        training_workspace.command(
            approval.asset_id,
            human_marked_rounds=(1,),
        )
    )

    assert status.rounds[0].model_retention_reasons == (
        "baseline",
        "human_marked",
    )
    assert list((training_workspace.memory_root / "models").iterdir()) == []
