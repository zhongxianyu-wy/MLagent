import json
from pathlib import Path

from src.agent.main import main


class RecordingPlanningCore:
    def __init__(self):
        self.record_commands = []
        self.approve_commands = []

    def record_exploration_plan(self, command):
        self.record_commands.append(command)
        return JsonResult(
            {
                "asset_type": "exploration_plan_event",
                "asset_id": "plan-event-1",
                "plan_id": command.plan_id,
                "state": "pending_review",
            }
        )

    def approve_exploration_plan(self, command):
        self.approve_commands.append(command)
        return JsonResult(
            {
                "asset_type": "exploration_plan_approval",
                "asset_id": "approval-1",
                "plan_id": command.plan_id,
                "decision": "approved",
            }
        )


class JsonResult:
    def __init__(self, payload):
        self.payload = payload

    def to_dict(self):
        return self.payload


def test_design_and_explore_record_parses_claude_plan_into_domain_command(
    tmp_path,
    capsys,
):
    core = RecordingPlanningCore()
    plan_path = tmp_path / "plan.json"
    plan_path.write_text(json.dumps(plan_payload()), encoding="utf-8")
    code_root = tmp_path / "code"
    code_root.mkdir()

    exit_code = main(
        [
            "design-and-explore",
            "record",
            "--workspace-config",
            str(tmp_path / ".mlagent-workspace.json"),
            "--dataset-id",
            "ds-1",
            "--dataset-version",
            "1",
            "--plan-file",
            str(plan_path),
            "--code-root",
            str(code_root),
        ],
        domain_core_factory=lambda: core,
    )

    assert exit_code == 0
    command = core.record_commands[0]
    assert command.plan_id == "plan-1"
    assert command.dataset_id == "ds-1"
    assert command.dataset_version == 1
    assert command.rounds[1].optimization_direction == "feature_selection"
    assert command.risks == ("feature selection can overfit",)
    assert command.trusted_experience_ids == ("experience-approved",)
    assert command.pending_experience_ids == ("experience-pending",)
    assert command.candidate_code_paths == ("train.py",)
    assert json.loads(capsys.readouterr().out)["asset_id"] == "plan-event-1"


def test_design_and_explore_approve_requires_explicit_subcommand(
    tmp_path,
    capsys,
):
    core = RecordingPlanningCore()

    exit_code = main(
        [
            "design-and-explore",
            "approve",
            "--workspace-config",
            str(tmp_path / ".mlagent-workspace.json"),
            "--plan-id",
            "plan-1",
            "--code-root",
            str(tmp_path / "code"),
        ],
        domain_core_factory=lambda: core,
    )

    assert exit_code == 0
    assert core.approve_commands[0].plan_id == "plan-1"
    assert json.loads(capsys.readouterr().out)["decision"] == "approved"


def test_design_and_explore_rejects_malformed_plan_json(tmp_path, capsys):
    plan_path = tmp_path / "plan.json"
    plan_path.write_text("[]", encoding="utf-8")

    exit_code = main(
        [
            "design-and-explore",
            "record",
            "--dataset-id",
            "ds-1",
            "--dataset-version",
            "1",
            "--plan-file",
            str(plan_path),
            "--code-root",
            str(tmp_path),
        ],
        domain_core_factory=RecordingPlanningCore,
    )

    assert exit_code == 2
    assert json.loads(capsys.readouterr().out)["error"]["code"] == "invalid_plan_file"


def test_design_and_explore_skill_preserves_human_gate_and_sop_boundary():
    skill = Path(".claude/skills/design-and-explore/SKILL.md").read_text(
        encoding="utf-8"
    )

    assert "explicit human" in skill.lower()
    assert "read-only" in skill.lower()
    assert "never auto-approve" in skill.lower()
    assert "not an sop" in skill.lower()
    assert "build_estimator(context" in skill
    assert "sklearn-compatible estimator" in skill
    assert "must not replace" in skill
    assert "formal models" in skill.lower()


def plan_payload():
    return {
        "plan_id": "plan-1",
        "planning_session_id": "session-1",
        "user_direction": "Improve validation AUC",
        "baseline_hypothesis": "Fit a regularized baseline",
        "rounds": [
            {
                "round_number": 1,
                "hypothesis": "The baseline is stable",
                "optimization_direction": "baseline",
                "intended_changes": ["fit logistic regression"],
            },
            {
                "round_number": 2,
                "hypothesis": "Feature selection may improve AUC",
                "optimization_direction": "feature_selection",
                "intended_changes": ["rank features", "refit top features"],
            },
        ],
        "stop_conditions": ["target reached", "round budget exhausted"],
        "risks": ["feature selection can overfit"],
        "resource_limits": {"max_minutes": 30, "max_parallel_jobs": 1},
        "trusted_experience_ids": ["experience-approved"],
        "pending_experience_ids": ["experience-pending"],
        "excluded_pending_experience_ids": [],
        "candidate_code_paths": ["train.py"],
    }
