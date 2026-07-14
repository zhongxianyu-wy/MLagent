# Production CLI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn MLagent_v3 into a CLI-first internal product that can run real NGS feature-matrix machine-learning experiments end to end.

**Architecture:** Keep the CLI shell and `frontend_api/` services as the product boundary. Deterministic data intake, training, evaluation, trace persistence, and safety checks live behind those services; the LLM plans and explains but never fabricates metrics or writes artifacts directly.

**Tech Stack:** Python 3.11+, pytest, pandas, numpy, scikit-learn, optional xgboost, sqlite3, JSON/JSONL output artifacts, local muyu-search-mcp adapter boundary.

**Worktree Status:** `git status` reports this directory is not a git repository, so `git worktree` cannot be created without initializing git. Development proceeds in-place until a repository is initialized or the project is moved into an existing git checkout.

---

## File Structure

- `src/agent/main.py`: CLI entrypoint; dispatches to the interactive shell and product commands.
- `src/agent/chat_shell.py`: interactive loop, streaming output, session continuity.
- `src/frontend_api/conversation_service.py`: slash command routing, natural-language routing, ModeGuard enforcement, plan promotion.
- `src/agent/mode_guard.py`: deterministic capability gate used by runtime code.
- `src/data_intake/`: file inspection, Socratic state, standardization, splits, manifest JSON writing.
- `src/training/`: real preprocessing, feature selection, model fitting, prediction, and persistence helpers.
- `src/evaluation/`: k-fold evaluation, metrics, threshold selection, optional test reporting.
- `src/frontend_api/run_service.py`: run lifecycle, trace persistence, stop requests, output summaries.
- `src/agent/harness.py`: bounded exploration and strict reproduction harnesses.
- `src/skill_bridge/`: Skill registry, candidate generation, approval-gated publishing, optimization comparison.
- `src/research/`: muyu-search adapter and knowledge ingestion.
- `tests/fixtures/`: small NGS-like datasets and Skill fixtures for end-to-end CLI tests.

## Task 1: Runtime Routing and ModeGuard Enforcement

**Files:**
- Modify: `src/frontend_api/conversation_service.py`
- Modify: `src/agent/chat_shell.py`
- Test: `tests/integration/test_cli_runtime_product.py`

- [ ] **Step 1: Write the failing test**

```python
from pathlib import Path

from src.agent.slash_commands import load_harnesses
from src.frontend_api.conversation_service import ConversationService


class FakeRunService:
    def __init__(self):
        self.requests = []

    def start_run(self, request):
        self.requests.append(request)
        return {"experiment_id": "exp-1", "status": "running"}


class FakeMemoryService:
    def get_related_context(self, dataset_id, objective, top_k=5):
        return []


def test_natural_language_agent_turn_routes_through_mode_guard():
    runs = FakeRunService()
    service = ConversationService(
        run_service=runs,
        memory_service=FakeMemoryService(),
        harnesses=load_harnesses(Path("config/harnesses.toml")),
    )

    result = service.handle_turn("session-1", "运行 demo 数据的特征探索，目标 AUC")

    assert result["mode"] == "agent"
    assert result["domain_action"] == "explore"
    assert runs.requests[0]["mode"] == "agent"
    assert runs.requests[0]["domain_action"] == "explore"


def test_plan_turn_cannot_start_training_even_when_text_says_execute():
    runs = FakeRunService()
    service = ConversationService(run_service=runs, memory_service=FakeMemoryService())

    result = service.handle_turn("session-1", "/plan 设计并执行 demo AUC 探索")

    assert result["status"] == "draft"
    assert runs.requests == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_cli_runtime_product.py -q`

Expected: FAIL because natural-language agent turns are handled as ask mode or ModeGuard is not wired.

- [ ] **Step 3: Write minimal implementation**

Implement `ConversationService.handle_turn()` so it:

- parses slash commands first;
- uses `classify_runtime_mode()` for natural language;
- calls `ModeGuard.authorize()` before plan writes and agent runs;
- maps natural-language agent requests containing exploration keywords to the configured `explore` harness.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_cli_runtime_product.py -q`

Expected: PASS.

- [ ] **Step 5: Run affected tests**

Run: `uv run pytest tests/contract/test_mode_guard.py tests/integration/test_train_type1_routing.py tests/integration/test_plan_mode_socratic.py tests/integration/test_cli_runtime_product.py -q`

Expected: PASS.

## Task 2: Product Intake Manifest and Standardized Files

**Files:**
- Modify: `src/data_intake/explorer.py`
- Modify: `src/data_intake/socratic.py`
- Modify: `src/data_intake/manifest.py`
- Modify: `src/data_intake/splitter.py`
- Modify: `src/frontend_api/dataset_service.py`
- Test: `tests/integration/test_product_intake.py`

- [ ] **Step 1: Write the failing tests**

```python
import json
from pathlib import Path

import pandas as pd

from src.frontend_api.dataset_service import DatasetService


def test_intake_writes_manifest_and_standardized_files(tmp_path):
    service = DatasetService(output_root=str(tmp_path / "standardized"))
    inspection = service.inspect_path("tests/fixtures/data_intake/clear")

    manifest = service.build_manifest(inspection.session_id)
    manifest_path = Path(tmp_path, "standardized", manifest.dataset_id, "manifest.json")

    assert manifest_path.exists()
    payload = json.loads(manifest_path.read_text())
    assert payload["dataset_id"] == manifest.dataset_id
    assert Path(payload["train_feature_path"]).exists()
    assert Path(payload["train_label_path"]).exists()
    assert payload["split_strategy"] in {"provided", "random", "train_only"}


def test_intake_random_split_creates_train_and_test_files(tmp_path):
    service = DatasetService(output_root=str(tmp_path / "standardized"))
    inspection = service.inspect_path("tests/fixtures/data_intake/clear")

    manifest = service.build_manifest(
        inspection.session_id,
        split_strategy="random",
        split_ratio=0.4,
        random_seed=7,
    )

    train_labels = pd.read_csv(manifest.train_label_path)
    test_labels = pd.read_csv(manifest.test_label_path)
    assert len(train_labels) + len(test_labels) == 6
    assert len(test_labels) == 2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_product_intake.py -q`

Expected: FAIL because `build_manifest()` does not accept split options and does not write `manifest.json`.

- [ ] **Step 3: Write minimal implementation**

Use pandas to read features and labels, validate sample IDs, optionally create deterministic random train/test splits, write standardized CSVs, write `manifest.json`, and keep existing clear/ambiguous Socratic behavior.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_product_intake.py -q`

Expected: PASS.

## Task 3: Real K-Fold Model Evaluation

**Files:**
- Create: `src/training/modeling.py`
- Modify: `src/evaluation/cv.py`
- Test: `tests/integration/test_real_training_pipeline.py`

- [ ] **Step 1: Write the failing test**

```python
import pandas as pd

from src.evaluation.cv import cross_validate
from src.models import EvaluationConfig
from src.training.modeling import SklearnModelTrainer


def test_sklearn_trainer_runs_real_kfold_predictions():
    features = pd.DataFrame(
        {
            "f1": [0, 0, 1, 1, 2, 2, 3, 3],
            "f2": [0, 1, 0, 1, 2, 3, 2, 3],
        }
    )
    labels = [0, 0, 0, 0, 1, 1, 1, 1]
    trainer = SklearnModelTrainer(model_type="logistic_regression", random_seed=11)

    result = cross_validate(
        features.values.tolist(),
        labels,
        EvaluationConfig(
            metric="auc",
            k_folds=2,
            target_specificity=None,
            threshold_policy="youden",
            use_test_if_available=True,
        ),
        trainer.predict_fold,
    )

    assert len(result.validation_scores) == len(labels)
    assert result.metrics["auc"] >= 0.75
    assert 0.0 <= result.threshold.threshold <= 1.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_real_training_pipeline.py -q`

Expected: FAIL because `src/training/modeling.py` does not exist.

- [ ] **Step 3: Write minimal implementation**

Implement `SklearnModelTrainer.predict_fold()` using scikit-learn logistic regression with a scaler pipeline and `predict_proba`.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_real_training_pipeline.py -q`

Expected: PASS.

## Task 4: Real Exploration Harness With Persisted Outputs

**Files:**
- Modify: `src/agent/harness.py`
- Modify: `src/frontend_api/run_service.py`
- Create: `src/training/dataset_loader.py`
- Test: `tests/integration/test_real_explore_cli.py`

- [ ] **Step 1: Write the failing test**

```python
import json
from pathlib import Path

from src.agent.harness import ExplorationHarness
from src.frontend_api.run_service import RunService


def test_exploration_writes_real_rounds_and_best_config(tmp_path):
    output_root = tmp_path / "outputs"
    harness = ExplorationHarness(output_root=str(output_root), clock=lambda: 100)
    service = RunService(exploration_harness=harness, id_factory=lambda: "exp-real", clock=lambda: 100)

    run = service.start_run(
        {
            "mode": "exploration",
            "dataset_id": "clear",
            "manifest_path": "tests/fixtures/product_datasets/clear/manifest.json",
            "max_rounds": 2,
            "guidance_metric_name": "auc",
            "k_folds": 2,
        }
    )

    assert run.status == "completed"
    rounds_path = output_root / "exp-real" / "rounds.jsonl"
    best_path = output_root / "exp-real" / "best_config.json"
    assert rounds_path.exists()
    assert best_path.exists()
    rows = [json.loads(line) for line in rounds_path.read_text().splitlines()]
    assert len(rows) == 2
    assert rows[0]["cv_metrics"]["auc"] >= 0.5
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_real_explore_cli.py -q`

Expected: FAIL because `ExplorationHarness` does not load manifests or write output artifacts.

- [ ] **Step 3: Write minimal implementation**

Load standardized CSVs from manifest, run two real strategy combinations, create `ExperimentRoundTrace` objects, write `rounds.jsonl`, `best_config.json`, `metrics.json`, and mark the run completed.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_real_explore_cli.py -q`

Expected: PASS.

## Task 5: CLI Product Commands Use Real Services

**Files:**
- Modify: `src/agent/main.py`
- Test: `tests/integration/test_product_cli_commands.py`

- [ ] **Step 1: Write the failing tests**

```python
from pathlib import Path

from src.agent.main import main


def test_research_without_service_returns_actionable_error():
    assert main(["research", "--target", "paper"]) != 0


def test_explore_command_runs_real_service_after_intake(tmp_path):
    intake_code = main([
        "intake",
        "tests/fixtures/data_intake/clear",
        "--output-root",
        str(tmp_path / "standardized"),
        "--split-strategy",
        "random",
        "--split-ratio",
        "0.4",
    ])
    assert intake_code == 0
    manifest_path = tmp_path / "standardized" / "clear" / "manifest.json"
    assert manifest_path.exists()

    explore_code = main([
        "explore",
        "--manifest-path",
        str(manifest_path),
        "--max-rounds",
        "1",
        "--output-root",
        str(tmp_path / "outputs"),
    ])

    assert explore_code == 0
    assert Path(tmp_path, "outputs").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_product_cli_commands.py -q`

Expected: FAIL because CLI arguments and no-op command behavior are not productized.

- [ ] **Step 3: Write minimal implementation**

Add explicit parser helpers for `intake`, `explore`, and unsupported product commands. Unsupported commands return non-zero with actionable messages instead of silent success.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_product_cli_commands.py -q`

Expected: PASS.

## Task 6: Strict Skill Reproduction Product Path

**Files:**
- Modify: `src/agent/harness.py`
- Modify: `src/frontend_api/skill_service.py`
- Test: `tests/integration/test_product_reproduce_cli.py`

- [ ] **Step 1: Write failing tests**

Verify a fixture Skill reproduces on a matching manifest and fails clearly when required features are absent.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_product_reproduce_cli.py -q`

Expected: FAIL until reproduction loads manifests and validates feature requirements.

- [ ] **Step 3: Implement minimal reproduction**

Read Skill metadata, load manifest, validate required features, run declared preprocessing/model/evaluation, write reproduction summary and traces.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_product_reproduce_cli.py -q`

Expected: PASS.

## Task 7: Interactive Validation Pause Product Path

**Files:**
- Modify: `src/frontend_api/run_service.py`
- Modify: `src/agent/control_center.py`
- Test: `tests/integration/test_product_interact_cli.py`

- [ ] **Step 1: Write failing test**

Verify `/interact` or CLI `interact` runs exactly one real validation round and returns paused status with `awaiting_user_instruction`.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_product_interact_cli.py -q`

Expected: FAIL until real one-round validation is wired.

- [ ] **Step 3: Implement minimal one-round validation**

Reuse exploration execution with `max_rounds=1`, preserve the user instruction as direction, and force paused status after trace persistence.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_product_interact_cli.py -q`

Expected: PASS.

## Task 8: Skill Distillation and Approval Gate

**Files:**
- Modify: `src/skill_bridge/generator.py`
- Modify: `src/skill_bridge/darwin_adapter.py`
- Modify: `src/frontend_api/skill_service.py`
- Test: `tests/integration/test_product_distill.py`

- [ ] **Step 1: Write failing test**

Verify notebook distillation creates a structured `SKILL.md`, runs validation/iteration, and remains pending human review.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_product_distill.py -q`

Expected: FAIL until candidate content and iteration status are product-grade.

- [ ] **Step 3: Implement minimal product candidate generation**

Extract notebook headings, code cells, method summary, inputs, outputs, evaluation policy, and write skill-creator-compatible frontmatter.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_product_distill.py -q`

Expected: PASS.

## Task 9: Research Ingestion Product Boundary

**Files:**
- Modify: `src/research/muyu_client.py`
- Modify: `src/frontend_api/research_service.py`
- Modify: `src/research/knowledge_ingest.py`
- Test: `tests/integration/test_product_research.py`

- [ ] **Step 1: Write failing test**

Verify research jobs record source metadata, method summary, feature notes, model notes, evaluation notes, reference code notes, and searchable memory entries.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_product_research.py -q`

Expected: FAIL until the service returns structured product artifacts.

- [ ] **Step 3: Implement minimal structured research adapter**

Keep external search behind an injectable adapter. The offline default must return explicit unavailable status unless a client result is injected, avoiding fake successful research.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_product_research.py -q`

Expected: PASS.

## Task 10: Product Smoke Test and Readiness Gate

**Files:**
- Create: `tests/integration/test_product_smoke_cli.py`
- Modify: `docs/superpowers/tasks/2026-05-27-production-cli-tasks.md`
- Modify: `specs/001-ngs-ml-agent/quickstart.md`

- [ ] **Step 1: Write failing smoke test**

Run intake and one-round exploration from CLI on the fixture dataset, then assert `manifest.json`, `run_summary.json`, `rounds.jsonl`, and `best_config.json` exist.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_product_smoke_cli.py -q`

Expected: FAIL until all product paths are connected.

- [ ] **Step 3: Implement missing glue only**

Fix only the smallest remaining CLI/service integration gaps exposed by the smoke test.

- [ ] **Step 4: Run full product verification**

Run: `uv run pytest tests/ --cov=src --cov-report=term-missing`

Expected: PASS.

Run one manual fixture command:

```bash
uv run python -m src.agent.main intake tests/fixtures/data_intake/clear --output-root /private/tmp/mlagent_product_standardized_trainonly --split-strategy train_only
uv run python -m src.agent.main explore --manifest-path /private/tmp/mlagent_product_standardized_trainonly/clear/manifest.json --max-rounds 1 --output-root /private/tmp/mlagent_product_outputs_trainonly
```

Expected: exit code 0 for both commands and output artifacts under `/private/tmp/mlagent_product_outputs_trainonly`.

Follow-up hardening: add Socratic or non-interactive handling for tiny random splits where the requested k-fold value exceeds the post-split minority class count.

---

## Self-Review

- Spec coverage: The plan covers CLI runtime, safety, intake, planning, exploration, training, reproduction, interaction, distillation, research, output artifacts, and readiness verification.
- Known intentional deferral: frontend UI implementation remains out of scope, but service boundaries remain intact.
- Worktree gap: The user requested worktrees; current filesystem is not a git repository, so real git worktrees cannot be created yet.
- Placeholder scan: No TBD/TODO placeholders are present. Later tasks 6-10 are deliberately less code-prescriptive than tasks 1-5 because their exact implementation depends on product primitives created in tasks 1-5, but each still has concrete files, commands, and expected behavior.
