from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.domain.core import DomainCore
from src.domain.models import (
    ApproveExplorationPlanCommand,
    BootstrapMemoryCommand,
    ConfirmDatasetCommand,
    ExecuteExplorationCommand,
    ExplorationRound,
    RecordExplorationPlanCommand,
)
from src.domain.run_repository import RunRepository, RunStartSpec


@pytest.fixture
def run_status_workspace(tmp_path, monkeypatch):
    core = DomainCore(
        id_factory=lambda: "tmr-1",
        dataset_id_factory=lambda: "ds-1",
        exploration_event_id_factory=lambda: "plan-event-1",
        exploration_approval_id_factory=lambda: "approval-1",
        clock=lambda: "2026-07-15T00:00:00Z",
    )
    connection_path = tmp_path / ".mlagent-workspace.json"
    snapshot = core.bootstrap_memory(
        BootstrapMemoryCommand(
            repository_path=tmp_path / "team-memory",
            actor_id="alice",
            connection_path=connection_path,
        )
    )
    features, labels = write_pair(tmp_path)
    core.confirm_dataset(
        ConfirmDatasetCommand(
            connection_path=connection_path,
            feature_path=features,
            label_path=labels,
            sample_id_col="sample_id",
            label_col="group",
            task_type="binary",
            positive_class="case",
            primary_metric="roc_auc",
            split_strategy="train_only",
            target_metric=0.91,
        )
    )
    code_root = tmp_path / "code"
    code_root.mkdir()
    training_code = (
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
        "    ])\n"
    )
    (code_root / "train.py").write_text(training_code, encoding="utf-8")
    core.record_exploration_plan(
        RecordExplorationPlanCommand(
            connection_path=connection_path,
            code_root=code_root,
            dataset_id="ds-1",
            dataset_version=1,
            plan_id="plan-1",
            planning_session_id="session-1",
            user_direction="Improve validation AUC",
            baseline_hypothesis="Fit a regularized baseline",
            rounds=(
                ExplorationRound(
                    round_number=1,
                    hypothesis="The baseline is stable",
                    optimization_direction="baseline",
                    intended_changes=("fit logistic regression",),
                ),
                ExplorationRound(
                    round_number=2,
                    hypothesis="Feature selection may improve validation AUC",
                    optimization_direction="feature_selection",
                    intended_changes=("rank features", "refit top features"),
                ),
            ),
            stop_conditions=("target reached", "round budget exhausted"),
            risks=("validation overfitting",),
            resource_limits={"max_minutes": 30, "max_parallel_jobs": 1},
            trusted_experience_ids=(),
            pending_experience_ids=(),
            excluded_pending_experience_ids=(),
            experience_applicability={},
            candidate_code_paths=("train.py",),
        )
    )
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection_path))
    monkeypatch.setenv("MLAGENT_CODE_ROOT", str(code_root))
    return RunStatusWorkspace(
        core=core,
        connection_path=connection_path,
        code_root=code_root,
        training_code=training_code,
        memory_root=tmp_path / "team-memory",
        capacity=snapshot.capacity,
    )


class RunStatusWorkspace:
    def __init__(
        self,
        core,
        connection_path,
        code_root,
        training_code,
        memory_root,
        capacity,
    ):
        self.core = core
        self.connection_path = connection_path
        self.code_root = code_root
        self.training_code = training_code
        self.memory_root = memory_root
        self.capacity = capacity

    def load_app(self):
        app = AppTest.from_file(
            Path("src/ui/app.py").resolve(),
            default_timeout=5,
        ).run()
        return app.sidebar.radio[0].set_value("Run Status").run()

    def approve(self):
        return self.core.approve_exploration_plan(
            ApproveExplorationPlanCommand(
                connection_path=self.connection_path,
                code_root=self.code_root,
                plan_id="plan-1",
            )
        )

    def seed_completed_run(self):
        approval = self.approve()
        return self.core.execute_exploration(
            ExecuteExplorationCommand(
                connection_path=self.connection_path,
                code_root=self.code_root,
                dataset_id="ds-1",
                dataset_version=1,
                plan_id="plan-1",
                approval_id=approval.asset_id,
                entrypoint_path="train.py",
            )
        )

    def seed_running_run(self):
        review = self.core.get_exploration_review(
            self.connection_path,
            self.code_root,
            "plan-1",
        )
        approval = self.approve()
        plan = review.plan
        runs = RunRepository(self.memory_root)
        runs.start_run(
            RunStartSpec(
                run_id="run-live",
                dataset_id=plan.dataset_id,
                dataset_version=plan.dataset_version,
                dataset_content_fingerprint=plan.dataset_content_fingerprint,
                dataset_version_fingerprint=plan.dataset_version_fingerprint,
                plan_id=plan.plan_id,
                plan_event_id=plan.asset_id,
                plan_fingerprint=plan.plan_fingerprint,
                approval_id=approval.asset_id,
                approval_fingerprint=approval.approval_fingerprint,
                code_fingerprint=plan.code_fingerprint,
                user_direction=plan.user_direction,
                stop_conditions=plan.stop_conditions,
                primary_metric_name=plan.primary_metric,
                target_metric_value=plan.target_metric,
                expected_round_count=len(plan.rounds),
            ),
            actor_id="alice",
            capacity=self.capacity,
        )
        runs.activate_run("run-live")
        return runs


def test_run_status_renders_plan_confidence_code_and_approval(
    run_status_workspace,
):
    app = run_status_workspace.load_app()

    assert not app.exception
    assert app.subheader[0].value == "Run Status"
    metrics = {(metric.label, metric.value) for metric in app.metric}
    assert ("Approval", "Pending review") in metrics
    assert ("Training gate", "Blocked") in metrics
    assert ("Rounds", "2") in metrics
    assert ("Target", "0.91") in metrics
    markdown = "\n".join(item.value for item in app.markdown)
    assert "Trusted Experience" in markdown
    assert "Pending Experience (low confidence)" in markdown
    assert "Excluded Pending Experience" in markdown
    assert "feature_selection" in markdown
    assert "Risks" in markdown
    assert app.code[0].value == run_status_workspace.training_code.strip()
    assert find_button(app, "Approve current plan and code") is not None


def test_run_status_approval_refreshes_to_approved(run_status_workspace):
    app = run_status_workspace.load_app()

    app = find_button(app, "Approve current plan and code").click().run()

    assert not app.exception
    assert any(
        metric.label == "Approval" and metric.value == "Approved"
        for metric in app.metric
    )
    assert any(
        metric.label == "Training gate" and metric.value == "Authorized"
        for metric in app.metric
    )
    assert find_button(app, "Approve current plan and code").disabled is True


def test_run_status_marks_changed_code_as_stale(run_status_workspace):
    run_status_workspace.approve()
    (run_status_workspace.code_root / "train.py").write_text(
        "print('changed after approval')\n",
        encoding="utf-8",
    )

    app = run_status_workspace.load_app()

    assert not app.exception
    assert any(
        metric.label == "Approval" and metric.value == "Approval stale"
        for metric in app.metric
    )
    assert any("changed" in warning.value.lower() for warning in app.warning)
    assert find_button(app, "Approve current plan and code").disabled is True


def test_run_status_readiness_check_cannot_bypass_approval(run_status_workspace):
    app = run_status_workspace.load_app()

    app = find_button(app, "Verify training readiness").click().run()

    assert not app.exception
    assert any(
        "plan_approval_required" in error.value for error in app.error
    )


def test_run_status_renders_live_curve_rounds_target_and_retention(
    run_status_workspace,
):
    status = run_status_workspace.seed_completed_run()

    app = run_status_workspace.load_app()

    assert not app.exception
    metrics = {(metric.label, metric.value) for metric in app.metric}
    assert ("Run state", "Completed") in metrics
    assert ("Best", f"{status.best_primary_metric_value:g}") in metrics
    assert ("Target", "0.91") in metrics
    assert app.get("arrow_vega_lite_chart") or app.get("vega_lite_chart")
    tables = [element.value for element in app.dataframe]
    assert any("feature_selection" in table.to_string() for table in tables)
    assert any("stage_best" in table.to_string() for table in tables)
    assert find_button(app, "Stop Run").disabled is True


def test_active_run_stop_button_records_domain_stop_request(run_status_workspace):
    runs = run_status_workspace.seed_running_run()
    try:
        app = run_status_workspace.load_app()
        stop = find_button(app, "Stop Run")
        assert stop.disabled is False

        app = stop.click().run()

        assert not app.exception
        status = run_status_workspace.core.get_run_status(
            run_status_workspace.connection_path,
            "run-live",
        )
        assert status.stop_requested is True
    finally:
        runs.deactivate_run("run-live")


def find_button(app, label):
    return next(button for button in app.button if button.label == label)


def write_pair(root: Path):
    sample_ids = [f"s{index:02d}" for index in range(12)]
    feature_path = root / "features.csv"
    label_path = root / "labels.csv"
    pd.DataFrame(
        {
            "sample_id": sample_ids,
            "f1": [index / 10 for index in range(12)],
            "f2": list(range(12)),
        }
    ).to_csv(feature_path, index=False)
    pd.DataFrame(
        {
            "sample_id": sample_ids,
            "group": ["case"] * 6 + ["control"] * 6,
        }
    ).to_csv(label_path, index=False)
    return feature_path, label_path
