# Frozen Training Instance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Execute an approved binary or multiclass Exploration Plan from frozen reviewed code, seal every attempted round as an immutable Training Instance, and expose its real-time Run projection in the existing UI.

**Architecture:** `DomainCore` rechecks the Issue #4 approval and delegates execution to a focused Run coordinator. `RunRepository` owns append-only Raw Record events, frozen code packages, atomic instance sealing, tamper checks, model retention, and derived Run Status. A subprocess worker imports only the frozen approved entrypoint and performs deterministic sklearn evaluation; CLI and Streamlit remain adapters over the Domain Core.

**Tech Stack:** Python 3.11+, dataclasses, pathlib, JSON/CSV, hashlib, fcntl, subprocess, pandas, scikit-learn, joblib, Streamlit, pytest, local Git fixtures

---

## File Map

- `src/domain/models.py`: public commands and immutable Run/Training Instance query snapshots.
- `src/domain/run_repository.py`: append-only events, code freeze, pending packages, sealing, loading, recovery, retention, and status projection.
- `src/domain/run_execution.py`: approved-plan orchestration and terminal state decisions.
- `src/domain/core.py`: single public command/query boundary and exact Issue #4 authorization reuse.
- `src/training/executor.py`: worker process lifecycle, timeout, stop polling, and bounded errors.
- `src/training/classification_worker.py`: frozen entrypoint loading, real binary/multiclass evaluation, prediction and model output.
- `src/agent/main.py`: authoritative `explore` execution and structured output.
- `.claude/skills/design-and-explore/SKILL.md`: generated-entrypoint contract used by Claude Code.
- `src/ui/app.py`: two-second Run Status projection, trend, round table, best/target, retention, and stop action.
- `tests/fixtures/training/estimator.py`: deterministic approved-code fixture implementing `build_estimator`.
- `tests/unit/test_run_models.py`: state and public-model invariants.
- `tests/unit/test_classification_worker.py`: deterministic metrics and contract failures.
- `tests/integration/test_run_repository.py`: immutable storage, event order, retention, tamper, and recovery.
- `tests/integration/test_domain_core_training_instance.py`: end-to-end lifecycle through Domain Core.
- `tests/integration/test_real_governed_training.py`: real binary and multiclass subprocess runs.
- `tests/integration/test_explore_cli.py`: default authoritative CLI execution.
- `tests/integration/test_run_status_ui.py`: live Run projection and stop controls.

### Task 1: Define Public Run Contracts

**Files:**
- Modify: `src/domain/models.py`
- Create: `tests/unit/test_run_models.py`

- [ ] **Step 1: Write failing contract tests**

```python
from pathlib import Path

from src.domain.models import ExecuteExplorationCommand, TrainingInstanceSnapshot


def test_execute_command_keeps_governed_references_explicit():
    command = ExecuteExplorationCommand(
        connection_path=Path(".mlagent-workspace.json"),
        code_root=Path("code"),
        dataset_id="ds-1",
        dataset_version=1,
        plan_id="plan-1",
        approval_id="approval-1",
        entrypoint_path="train.py",
    )
    assert command.dataset_version == 1
    assert command.plan_id == "plan-1"


def test_failed_instance_cannot_claim_reproducible_evidence():
    snapshot = instance_snapshot(
        state="failed",
        reproducible_evidence=False,
        primary_metric_value=None,
    )
    assert snapshot.sop_source_eligible is False
```

- [ ] **Step 2: Run the focused tests and verify RED**

Run: `/Volumes/exp/project/MLagent_v3/.venv/bin/pytest tests/unit/test_run_models.py -q`

Expected: FAIL because the Run commands and snapshots do not exist.

- [ ] **Step 3: Add immutable command and snapshot dataclasses**

```python
@dataclass(frozen=True)
class ExecuteExplorationCommand:
    connection_path: Path
    code_root: Path
    dataset_id: str
    dataset_version: int
    plan_id: str
    approval_id: str
    entrypoint_path: str | None = None
    human_marked_rounds: tuple[int, ...] = ()


@dataclass(frozen=True)
class RequestRunStopCommand:
    connection_path: Path
    run_id: str
    reason: str = "user_stop"


@dataclass(frozen=True)
class RecoverRunCommand:
    connection_path: Path
    run_id: str
    action: str


@dataclass(frozen=True)
class TrainingInstanceSnapshot:
    asset_id: str
    asset_path: str
    run_id: str
    round_number: int
    state: str
    reproducible_evidence: bool
    sop_source_eligible: bool
    dataset_version_fingerprint: str
    code_fingerprint: str
    configuration_fingerprint: str
    environment_fingerprint: str
    split_fingerprint: str
    random_seed: int
    parent_instance_id: str | None
    optimization_direction: str
    primary_metric_name: str
    primary_metric_value: float | None
    metrics: dict[str, float]
    model_fingerprint: str | None
    model_retention_reasons: tuple[str, ...]
    model_path: str | None
    error_code: str | None
    error_summary: str | None
    started_at: str
    ended_at: str
    duration_ms: int
```

Also add `RunRoundSnapshot`, `RunStatusSnapshot`, and `TrainingExecutionResult`. Keep `to_dict()` behavior
through the existing `_to_jsonable` helper and validate failed-instance invariants at construction.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `/Volumes/exp/project/MLagent_v3/.venv/bin/pytest tests/unit/test_run_models.py tests/unit/test_exploration_models.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/domain/models.py tests/unit/test_run_models.py
git commit -m "feat(domain): define governed run contracts"
```

### Task 2: Build Append-Only Run And Instance Storage

**Files:**
- Create: `src/domain/run_repository.py`
- Create: `tests/integration/test_run_repository.py`

- [ ] **Step 1: Write failing repository tests**

```python
def test_sealed_instance_is_immutable_and_reloads(run_repository_fixture):
    repository, prepared, result = run_repository_fixture.completed()
    sealed = repository.seal_instance(prepared, result)
    assert repository.load_instance(sealed.run_id, sealed.asset_id) == sealed
    with pytest.raises(WorkspaceError, match="already exists"):
        repository.seal_instance(prepared, result)


def test_events_are_causal_and_minimal(run_repository_fixture):
    repository = run_repository_fixture.repository
    repository.start_run(run_repository_fixture.start_spec)
    repository.request_stop("run-1", actor_id="alice")
    events = repository.list_events("run-1")
    assert events[1].previous_event_id == events[0].asset_id
    payload = json.loads((repository.root / events[1].asset_path).read_text())
    assert set(payload).isdisjoint({"prompt", "conversation", "stdout", "stderr"})
```

Cover final-file tampering, manifest tampering, parent references, pending detection, recovery close, local
causal serialization, and capacity rejection.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `/Volumes/exp/project/MLagent_v3/.venv/bin/pytest tests/integration/test_run_repository.py -q`

Expected: FAIL because `RunRepository` does not exist.

- [ ] **Step 3: Implement canonical event and package persistence**

```python
RUN_EVENT_ROOT = Path("raw-records/runs")
RUN_ROOT = Path("runs")
TERMINAL_STATES = {"completed", "failed", "timed_out", "stopped"}
ALLOWED_EVENT_FIELDS = {
    "asset_type", "asset_id", "schema_version", "run_id", "event_type",
    "state", "previous_event_id", "dataset_id", "dataset_version",
    "plan_id", "plan_event_id", "approval_id", "instance_id",
    "round_number", "parent_instance_id", "hypothesis",
    "optimization_direction", "primary_metric_name", "primary_metric_value",
    "reason_code", "error_summary", "evidence_refs", "created_at",
    "created_by", "event_fingerprint",
}
```

Implement canonical SHA-256 serialization, safe ID/path validation, `.mlagent-local/run-locks` locking,
atomic temporary-directory rename, manifest/file hash validation, and no-overwrite behavior. Reuse the
capacity values supplied by `MemoryRepository` and reject any retained file at or above `max_file_bytes`.

- [ ] **Step 4: Implement code freeze, retention, projection, and recovery**

`freeze_code_revision()` must copy only approved files and verify each hash before and after copy.
`prepare_instance()` must copy the exact split and write canonical input/environment files. `seal_instance()`
must retain baseline, stage-best, or human-marked models and remove other model binaries after hashing.
`status()` reconstructs rounds and terminal state from events and detects a nonterminal head or pending
directory as `recovery_required`.

- [ ] **Step 5: Run repository tests and verify GREEN**

Run: `/Volumes/exp/project/MLagent_v3/.venv/bin/pytest tests/integration/test_run_repository.py -q`

Expected: PASS, including immutable reload and recovery cases.

- [ ] **Step 6: Commit**

```bash
git add src/domain/run_repository.py tests/integration/test_run_repository.py
git commit -m "feat(memory): seal training instance evidence"
```

### Task 3: Execute Real Frozen Binary And Multiclass Code

**Files:**
- Create: `src/training/executor.py`
- Create: `src/training/classification_worker.py`
- Create: `tests/fixtures/training/estimator.py`
- Create: `tests/unit/test_classification_worker.py`
- Create: `tests/integration/test_real_governed_training.py`

- [ ] **Step 1: Add a reviewed-code fixture and failing worker tests**

```python
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import StandardScaler


def build_estimator(context):
    return Pipeline([
        ("scale", StandardScaler()),
        ("model", LogisticRegression(
            random_state=context["random_seed"],
            max_iter=500,
        )),
    ])
```

The tests must assert binary `roc_auc`, multiclass `macro_f1`/`roc_auc_ovr`, deterministic predictions,
missing `build_estimator`, non-estimator return, malformed output, and finite `[0, 1]` metrics.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `/Volumes/exp/project/MLagent_v3/.venv/bin/pytest tests/unit/test_classification_worker.py tests/integration/test_real_governed_training.py -q`

Expected: FAIL because the worker and executor are absent.

- [ ] **Step 3: Implement the deterministic worker**

```python
def evaluate(input_path: Path, output_path: Path) -> None:
    descriptor = json.loads(input_path.read_text(encoding="utf-8"))
    estimator = load_frozen_entrypoint(descriptor).build_estimator(
        descriptor["context"]
    )
    dataset = load_versioned_frames(descriptor)
    if descriptor["split_strategy"] == "train_only":
        predictions, metrics = out_of_fold_predictions(dataset, estimator)
    else:
        predictions, metrics = held_out_predictions(dataset, estimator)
    fitted = clone(estimator).fit(dataset.train_x, dataset.train_y)
    write_result(output_path, predictions, metrics, fitted)
```

Use `StratifiedKFold(shuffle=True, random_state=seed)`, sorted class semantics, `clone`, sklearn metrics,
`joblib.dump`, canonical JSON, and CSV with sample ID, observed label, predicted label, and probabilities.

- [ ] **Step 4: Implement controlled process execution**

```python
class SubprocessTrainingExecutor:
    def execute(self, prepared, stop_requested, timeout_seconds):
        process = subprocess.Popen(
            [sys.executable, "-m", "src.training.classification_worker",
             "--input", str(prepared.input_path),
             "--output", str(prepared.output_path)],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        return poll_and_classify(process, stop_requested, timeout_seconds)
```

Terminate then kill after a short grace period. Return stable `completed`, `failed`, `timed_out`, or
`stopped` results. Retain no full streams; normalize and cap the diagnostic fragment.

- [ ] **Step 5: Run worker tests and verify GREEN**

Run: `/Volumes/exp/project/MLagent_v3/.venv/bin/pytest tests/unit/test_classification_worker.py tests/integration/test_real_governed_training.py -q`

Expected: PASS with real subprocess training for binary and multiclass fixtures.

- [ ] **Step 6: Commit**

```bash
git add src/training/executor.py src/training/classification_worker.py tests/fixtures/training tests/unit/test_classification_worker.py tests/integration/test_real_governed_training.py
git commit -m "feat(training): run frozen classification code"
```

### Task 4: Orchestrate Approved Runs Through Domain Core

**Files:**
- Create: `src/domain/run_execution.py`
- Modify: `src/domain/core.py`
- Create: `tests/integration/test_domain_core_training_instance.py`

- [ ] **Step 1: Write failing end-to-end lifecycle tests**

```python
def test_approved_plan_executes_and_seals_instances(training_workspace):
    approval = training_workspace.approve()
    status = training_workspace.core.execute_exploration(
        training_workspace.execute_command(approval.asset_id)
    )
    assert status.state == "completed"
    assert status.rounds[0].instance_state == "completed"
    assert status.best_instance_id == status.rounds[0].instance_id


def test_denied_plan_creates_no_run(training_workspace):
    with pytest.raises(WorkspaceError, match="approval"):
        training_workspace.core.execute_exploration(
            training_workspace.execute_command("missing")
        )
    assert list((training_workspace.memory_root / "runs").glob("**/*")) == []
```

Add success, first-round failure, timeout, user stop, target stop, code edit after start, parent chaining,
explicit human retention, interrupted recovery resume/close, and failure SOP-ineligibility.

- [ ] **Step 2: Run lifecycle tests and verify RED**

Run: `/Volumes/exp/project/MLagent_v3/.venv/bin/pytest tests/integration/test_domain_core_training_instance.py -q`

Expected: FAIL because execution methods are missing.

- [ ] **Step 3: Implement `TrainingRunCoordinator`**

```python
for round_spec in remaining_rounds:
    if runs.stop_requested(run_id):
        return runs.stop(run_id, reason="user_stop")
    prepared = runs.prepare_instance(
        run=run,
        round_spec=round_spec,
        parent_instance_id=parent_instance_id,
        dataset=dataset,
        code_revision=code_revision,
        environment=environment,
    )
    result = executor.execute(
        prepared,
        stop_requested=lambda: runs.stop_requested(run_id),
        timeout_seconds=timeout_seconds,
    )
    instance = runs.seal_instance(prepared, result)
    if instance.state != "completed" or target_reached(instance, dataset):
        break
```

Terminal decisions must map exactly to `completed`, `failed`, `timed_out`, or `stopped`; target achievement
is a completed Run with reason `target_metric_reached`.

- [ ] **Step 4: Add Domain Core commands and queries**

`execute_exploration()` must call the same authoritative approval operation used by Issue #4 before
creating a Run. Add `get_run_status()`, `list_run_statuses()`, `request_run_stop()`, and `recover_run()`.
All paths and actors come from the workspace connection, not adapter-provided repository paths.

- [ ] **Step 5: Run lifecycle and prior authorization tests**

Run: `/Volumes/exp/project/MLagent_v3/.venv/bin/pytest tests/integration/test_domain_core_training_instance.py tests/contract/test_domain_core_exploration_plan.py tests/integration/test_pre_tool_use_training_gate.py -q`

Expected: PASS; blocked execution still writes only the existing minimal gate audit.

- [ ] **Step 6: Commit**

```bash
git add src/domain/run_execution.py src/domain/core.py tests/integration/test_domain_core_training_instance.py
git commit -m "feat(domain): execute approved exploration runs"
```

### Task 5: Route Claude Code CLI To Governed Execution

**Files:**
- Modify: `src/agent/main.py`
- Modify: `.claude/skills/design-and-explore/SKILL.md`
- Modify: `tests/integration/test_explore_cli.py`
- Modify: `tests/integration/test_design_and_explore_cli.py`

- [ ] **Step 1: Write failing CLI delegation tests**

```python
def test_authoritative_explore_executes_domain_run(confirmed_domain_core, capsys):
    confirmed_domain_core.execute_result = run_status("completed")
    code = main(authoritative_args(), domain_core_factory=lambda: confirmed_domain_core)
    assert code == 0
    assert confirmed_domain_core.execute_commands[0].approval_id == "approval-1"
    assert json.loads(capsys.readouterr().out)["state"] == "completed"
```

Preserve `explore_factory` as an adapter contract test seam. Assert `--max-rounds` still cannot override the
approved plan and a failed terminal Run returns exit code 2 with structured output.

- [ ] **Step 2: Run CLI tests and verify RED**

Run: `/Volumes/exp/project/MLagent_v3/.venv/bin/pytest tests/integration/test_explore_cli.py tests/integration/test_design_and_explore_cli.py -q`

Expected: FAIL because default authoritative execution still reports the Issue #5 placeholder.

- [ ] **Step 3: Replace the placeholder with `ExecuteExplorationCommand`**

```python
status = authoritative_core.execute_exploration(
    ExecuteExplorationCommand(
        connection_path=workspace_config,
        code_root=code_root,
        dataset_id=dataset_id,
        dataset_version=snapshot.version,
        plan_id=plan_id,
        approval_id=approval_id,
        entrypoint_path=_option(args, "--entrypoint", None),
    )
)
print(json.dumps(status.to_dict(), ensure_ascii=False, sort_keys=True))
return 0 if status.state == "completed" else 2
```

Do not route governed execution through legacy `RunService`, `ExplorationHarness`, MLflow, or episodic
memory.

- [ ] **Step 4: Document the generated-code contract in the Skill**

State that Claude Code completes the user direction without scientific scoring, generates an approved
Python entrypoint exposing `build_estimator(context)`, records it in `candidate_code_paths`, and never
auto-approves or calls this an SOP.

- [ ] **Step 5: Run CLI tests and verify GREEN**

Run: `/Volumes/exp/project/MLagent_v3/.venv/bin/pytest tests/integration/test_explore_cli.py tests/integration/test_design_and_explore_cli.py tests/integration/test_real_explore_cli.py -q`

Expected: PASS; legacy manifest behavior remains isolated.

- [ ] **Step 6: Commit**

```bash
git add src/agent/main.py .claude/skills/design-and-explore/SKILL.md tests/integration/test_explore_cli.py tests/integration/test_design_and_explore_cli.py
git commit -m "feat(cli): execute governed exploration runs"
```

### Task 6: Render Live Run Status

**Files:**
- Modify: `src/ui/app.py`
- Modify: `tests/integration/test_run_status_ui.py`
- Modify: `tests/contract/test_frontend_streamlit_contracts.py`

- [ ] **Step 1: Add failing Run Status UI tests**

```python
def test_run_status_renders_live_rounds_curve_and_target(run_status_workspace):
    run_status_workspace.seed_completed_run()
    app = run_status_workspace.load_app()
    assert not app.exception
    assert ("Run state", "Completed") in metric_pairs(app)
    assert ("Best", "0.87") in metric_pairs(app)
    assert ("Target", "0.91") in metric_pairs(app)
    assert len(app.line_chart) == 1
    assert "feature_selection" in markdown_text(app)
    assert "stage_best" in markdown_text(app)
```

Add active Stop button, parent instance, elapsed time, failure state, no-Run preapproval view, and mobile-safe
table tests.

- [ ] **Step 2: Run UI tests and verify RED**

Run: `/Volumes/exp/project/MLagent_v3/.venv/bin/pytest tests/integration/test_run_status_ui.py tests/contract/test_frontend_streamlit_contracts.py -q`

Expected: FAIL because only pre-Run plan review is rendered.

- [ ] **Step 3: Add a two-second Domain Core projection fragment**

```python
@st.fragment(run_every=2.0)
def _render_live_run(core, connection_path, run_id):
    status = core.get_run_status(connection_path, run_id)
    render_run_summary(status)
    render_performance_curve(status.performance_points)
    render_round_table(status.rounds)
```

Keep the approved plan and frozen code information visible. Use a Run selector when history exists, stable
metric columns, a line chart indexed by round, and a compact dataframe for direction/parent/state/duration.
The Stop button calls `DomainCore.request_run_stop()` and never edits event files directly.

- [ ] **Step 4: Run UI tests and verify GREEN**

Run: `/Volumes/exp/project/MLagent_v3/.venv/bin/pytest tests/integration/test_run_status_ui.py tests/contract/test_frontend_streamlit_contracts.py tests/integration/test_streamlit_workspace_shell.py -q`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/ui/app.py tests/integration/test_run_status_ui.py tests/contract/test_frontend_streamlit_contracts.py
git commit -m "feat(ui): monitor governed training runs"
```

### Task 7: Verify Acceptance, Review, And Publish

**Files:**
- Modify if required: `docs/superpowers/specs/2026-07-16-issue-5-training-instance-design.md`
- Modify if required: `docs/superpowers/plans/2026-07-16-issue-5-training-instance.md`

- [ ] **Step 1: Run focused acceptance suites**

Run:

```bash
/Volumes/exp/project/MLagent_v3/.venv/bin/pytest \
  tests/unit/test_run_models.py \
  tests/unit/test_classification_worker.py \
  tests/integration/test_run_repository.py \
  tests/integration/test_domain_core_training_instance.py \
  tests/integration/test_real_governed_training.py \
  tests/integration/test_explore_cli.py \
  tests/integration/test_run_status_ui.py -q
```

Expected: PASS.

- [ ] **Step 2: Run the full regression suite**

Run: `/Volumes/exp/project/MLagent_v3/.venv/bin/pytest -q`

Expected: all tests pass with no legacy regression.

- [ ] **Step 3: Inspect authoritative output and minimality**

Run a real temporary binary and multiclass workspace, then inspect `raw-records/runs` and `runs` with
`find`, `jq`, `du`, and SHA-256 checks. Confirm no complete stdout/stderr, chat, prompt, SOP, or formal
`models` asset was written.

- [ ] **Step 4: Run static repository checks**

Run:

```bash
git diff --check
git status --short
rg -n "T[B]D|T[O]DO|training_execution_not_implemented" src tests docs/superpowers/specs/2026-07-16-issue-5-training-instance-design.md
```

Expected: no whitespace errors, accidental generated files, placeholders, or Issue #5 execution stub.

- [ ] **Step 5: Perform code review and browser acceptance**

Review the Issue #4 merge-base diff for lifecycle bugs, unsafe paths, weak fingerprints, state ambiguity,
unbounded logs, and SOP/model boundary violations. Start Streamlit against a real fixture and verify desktop
and 390px mobile layouts, two-second updates, nonblank curve, no overlap, and Stop behavior.

- [ ] **Step 6: Commit review fixes, push, and update Issue #5**

```bash
git push -u origin feat/issue-5-training-instance
```

Replace `ready-for-agent` with `ready-for-human` and comment with branch, commits, focused/full test counts,
browser evidence, and the explicit statement that Issue #5 creates no SOP Version or Formal Model.
