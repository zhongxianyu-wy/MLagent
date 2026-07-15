from pathlib import Path

import pandas as pd
import pytest
from streamlit.testing.v1 import AppTest

from src.domain.core import DomainCore
from src.domain.models import (
    ApproveExplorationPlanCommand,
    BootstrapMemoryCommand,
    ConfirmDatasetCommand,
    ExplorationRound,
    RecordExplorationPlanCommand,
)


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
    core.bootstrap_memory(
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
    training_code = "print('reviewed baseline')\n"
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
            trusted_experience_ids=("experience-approved",),
            pending_experience_ids=(
                "experience-pending",
                "experience-excluded",
            ),
            excluded_pending_experience_ids=("experience-excluded",),
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
    )


class RunStatusWorkspace:
    def __init__(self, core, connection_path, code_root, training_code):
        self.core = core
        self.connection_path = connection_path
        self.code_root = code_root
        self.training_code = training_code

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
