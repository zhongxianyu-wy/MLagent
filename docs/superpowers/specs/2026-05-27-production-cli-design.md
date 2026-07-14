# Production CLI Design: NGS ML Experiment Agent

## Goal

Build MLagent_v3 into a CLI-first internal product for real NGS machine-learning experiments. The CLI must be usable by a researcher without a frontend: it should inspect prepared feature matrices and labels, clarify ambiguous inputs, standardize datasets, plan experiments through an LLM conversation, run real k-fold training, preserve every exploration round, reproduce approved Skills, support interactive validation, distill new Skill candidates, ingest research knowledge, and optimize Skills with human approval.

This phase intentionally postpones frontend UI work. Service boundaries must stay frontend-ready, but the product surface for this phase is the interactive CLI and its deterministic local outputs.

## Non-Goals

- Raw BAM, FASTQ, VCF, or upstream bioinformatics processing.
- Multi-user deployment, remote job queue, or web UI.
- Fully autonomous unrestricted command execution.
- Publishing or replacing approved Skills without human approval.
- Using test-set predictions or labels for threshold or candidate selection.

## Product Surface

The primary command is `mlagent` with no arguments. It opens a Claude Code-like shell with session memory and streaming responses.

Required shell modes:

- `ask`: normal LLM Q&A. It may write conversation history only. It cannot call project tools or mutate experiment state.
- `plan`: Socratic experiment planning. It may read memory summaries and create/update a validation plan, but cannot write model artifacts, launch training, mutate Skills, or run local commands.
- `agent`: executable mode. It may run intake, exploration, reproduction, validation, research, distillation, and Skill optimization after clarification and safety gates pass.

Required slash commands:

- `/ask <question>`
- `/plan <goal>`
- `/agent <goal or execute current plan>`
- `/intake <path> [natural-language constraints]`
- `/explore <dataset-ref> [objective and limits]`
- `/reproduce <skill-id> <dataset-ref>`
- `/interact <dataset-ref> <validation instruction>`
- `/distill --notebook <path>` or `/distill --run <experiment-id>`
- `/research <paper|repo|topic>`
- `/skill_opt <skill-id> [dataset-ref and limits]`
- Configured aliases such as `/train_type1`

Slash commands force their functional harness and must not depend on broad intent recognition. Natural-language-only turns may route to ask, plan, or agent, but must pass deterministic mode and safety checks.

## Core Workflow

### 1. Intake

Input may be a file or directory containing one or more CSV/TSV/XLSX feature matrices, label/group files, optional split files, and optional test sets.

The intake engine must:

- Detect candidate feature, label, train, test, and split files.
- Infer sample ID column, label column, feature orientation, and binary labels when confidence is high.
- Ask one Socratic clarification question at a time when confidence is low.
- Validate sample alignment and report unmatched samples before dropping anything.
- Support provided train/test splits or reproducible random split with configured ratio and seed.
- Write a standard dataset directory containing `manifest.json`, train/test feature files, train/test label files when applicable, and an intake report.

### 2. Planning

Plan mode creates a `ValidationPlan` containing:

- Dataset assumptions and unresolved questions.
- Metric: AUC, accuracy, or sensitivity at target specificity.
- k-fold value and threshold policy.
- Stop conditions: target metric, max rounds, max runtime, patience, user stop.
- Candidate directions ordered by the product rule: preprocessing first, feature subset selection second, model/hyperparameter optimization last.
- Memory and Skill context that informed the plan.

Plan mode does not execute the plan. A ready plan can be promoted to agent mode only after explicit confirmation.

### 3. Exploration

Agent exploration must run real local training. Each round has:

- LLM or harness-proposed direction.
- Preprocessing strategy such as none, standardization, robust scaling, min-max scaling, or binarization.
- Feature subset strategy such as low variance, correlation filter, univariate test, model importance, recursive selection, or stability selection.
- Model strategy, initially logistic regression, random forest, XGBoost when installed, and SVM where appropriate.
- k-fold training on training data only.
- Threshold chosen from concatenated validation-fold predictions.
- Optional final test metrics using the selected threshold.
- Structured trace persisted for CLI display, future frontend use, memory writeback, and Skill distillation.

Exploration stops when any configured stop condition is met.

### 4. Reproduction

Strict reproduction executes an approved Skill without exploratory changes. Only declared dataset adaptation is allowed: path mapping, column mapping, label mapping, and feature name mapping when the Skill explicitly permits it.

The run must fail clearly if required features, preprocessing assumptions, or evaluation requirements are missing.

### 5. Interactive Validation

Interactive validation executes one user-directed experiment, returns metrics and interpretation, then pauses. It must not continue into autonomous exploration without another user instruction.

### 6. Skill Distillation and Optimization

Skill distillation supports:

- Notebook to SkillCandidate.
- Best exploration or interactive run to SkillCandidate.

Skill candidates must follow `skill-creator` structure, run darwin-style evaluate/improve/test/keep-or-revert, and remain pending until human approval.

`/skill_opt` backs up the current Skill, creates an optimized candidate, runs old/new parallel modeling tests, compares runtime, consistency, and modeling performance, and waits for user approval before replacing the approved Skill. Candidate selection uses training k-fold metrics only; test metrics are report-only.

### 7. Research Ingestion

Research uses the local muyu-search-mcp workflow. Targeted research accepts a paper, repository, or URL. Automatic research searches recent methods in feature engineering and modeling.

Research output enters semantic memory as knowledge with source metadata. It does not become a Skill unless explicitly distilled and approved.

## Architecture

### CLI Runtime

- `src/agent/main.py`: thin entrypoint only.
- `src/agent/chat_shell.py`: interactive shell loop, streaming display, session continuity.
- `src/frontend_api/conversation_service.py`: mode routing, slash command handling, plan promotion, and shell-facing responses.
- `src/agent/mode_guard.py`: mandatory runtime gate for all service calls.
- `src/agent/harness.py` and `config/harnesses.toml`: auditable functional harness registry.

### Deterministic Experiment Core

- `src/data_intake/`: inspection, clarification state, standardization, split generation, manifest writing.
- `src/training/`: preprocessing, feature selection, model runner, script adapters.
- `src/evaluation/`: k-fold, metrics, threshold selection, test-set reporting.
- `src/frontend_api/run_service.py`: run lifecycle, round traces, stop requests, status.
- `src/memory/episodic.py`: persistent run, trace, plan, and dataset state.

### Knowledge and Skill Layer

- `src/memory/semantic.py` and metadata index: searchable experience and knowledge.
- `src/skill_bridge/`: Skill registry, candidate generation, darwin adapter, optimization.
- `src/research/`: muyu-search client adapter and knowledge ingestion.

### Safety

- Ask and plan modes must be enforced in runtime code, not only in tests.
- Local command execution must pass command and path hooks.
- Files may be written only under approved project output roots unless explicitly approved.
- Long runs must honor max runtime and user stop.

## Output Layout

Each run writes under `experiments/outputs/<experiment_id>/`:

- `run_summary.json`
- `rounds.jsonl`
- `best_config.json`
- `metrics.json`
- `model/` for final model artifacts when applicable
- `reports/` for human-readable markdown summaries

Each standardized dataset writes under `experiments/standardized/<dataset_id>/`:

- `manifest.json`
- `train_features.csv`
- `train_labels.csv`
- Optional `test_features.csv`
- Optional `test_labels.csv`
- `intake_report.md`

## Testing Strategy

All behavior changes follow TDD.

Priority acceptance tests:

1. CLI no-argument shell can ask, plan, and agent-route with mode guard enforcement.
2. Intake fixture with separate feature and label files produces a manifest and standardized files.
3. Intake fixture without split can create deterministic train/test split.
4. k-fold runner trains a real sklearn model and selects threshold from validation predictions only.
5. `/explore` on a small NGS-like fixture produces real metrics, persisted traces, and a best config.
6. `/reproduce` executes a fixture Skill strictly and fails on missing required features.
7. `/interact` runs one requested validation and pauses.
8. `/distill` creates a pending SkillCandidate from notebook or best run.
9. `/research` ingests structured knowledge through the muyu adapter boundary.
10. `/skill_opt` creates a pending comparison report and does not replace Skills without approval.

Full product readiness requires `uv run pytest tests/ --cov=src --cov-report=term-missing` plus at least one end-to-end CLI fixture run.

## Implementation Order

1. Replace mock-only CLI paths with real services or explicit actionable errors.
2. Wire natural-language routing and ModeGuard into `ConversationService`.
3. Productize intake and manifest writing.
4. Implement real training/evaluation pipeline.
5. Replace mock exploration harness with bounded real exploration.
6. Persist run outputs and traces to disk and SQLite.
7. Productize strict Skill reproduction.
8. Productize interactive validation pause/resume.
9. Productize distillation, research ingestion, and `/skill_opt`.
10. Add internal CLI quickstart and smoke fixture.

## Readiness Criteria

The CLI is ready for internal use when:

- A researcher can standardize a fixture dataset from CLI without editing code.
- A researcher can run real exploration and inspect output files.
- Every round contains reproducible data, strategy, metrics, threshold, and rationale.
- Ask/plan/agent boundaries are enforced in runtime paths.
- Runs stop predictably and report why.
- Skill and research features are safe by default and approval-gated.
- The documented quickstart works on a clean local checkout.
