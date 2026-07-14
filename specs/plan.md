# Implementation Plan: NGS ML Experiment Agent

**Branch**: `001-ngs-ml-agent` | **Date**: 2026-05-25 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/001-ngs-ml-agent/spec.md`

## Summary

Build a local NGS machine-learning experiment agent that turns user-provided feature matrices and grouping labels into standardized datasets, runs controlled feature-engineering exploration, strictly reproduces approved Skills, supports interactive validation, distills new Skills, ingests external research knowledge, and exposes stable contracts for future frontend development. The technical approach is a Python 3.11+ single-project architecture with deterministic local evaluation, SQLite-backed traces, semantic memory, a Skill bridge, Anthropic-compatible LLM providers, and project-local muyu-search-mcp research integration.

## Technical Context

**Language/Version**: Python 3.11+

**Primary Dependencies**: pandas, numpy, scikit-learn, xgboost, anthropic-compatible HTTP client layer, mem0ai, chromadb, mlflow, nbformat, pydantic or dataclasses, streamlit later

**Storage**: SQLite for dataset manifests, run control, round traces, metadata index, Skill registry, and review state; ChromaDB/mem0 for semantic memory; filesystem for standardized datasets, model artifacts, notebooks, and Skill folders

**Testing**: pytest, pytest-cov; contract tests for service interfaces; integration tests for data intake, k-fold evaluation, threshold selection, memory-Skill bridge, and research ingestion

**Target Platform**: Local macOS/Linux workstation, single user, CPU training, 16GB+ RAM recommended

**Project Type**: Python CLI/library with service interfaces designed for later Streamlit or web frontend

**Performance Goals**: Data intake fixture completes under 30s; small 10-round fixture completes under 30s with mocked trainer; SQLite trace queries under 500ms for 1k rounds; semantic search under 2s for 1k memory entries

**Constraints**: Raw NGS BAM/VCF processing out of scope; original data must stay local; LLM only sees schema, summaries, candidate directions, and metrics; threshold selection never uses test predictions; Skills require human approval before publication

**Scale/Scope**: MVP supports local binary classification projects with one active user, one or more feature/label files, configurable k-fold, and dozens to hundreds of experiment rounds

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

The generated constitution is still templated. Until finalized, this feature applies project-specific gates:

- **Local data safety**: PASS. Plan keeps original matrices local and sends only summaries to the LLM.
- **Deterministic evaluation**: PASS. Metrics, thresholds, k-folds, and model artifacts are computed by local code.
- **Traceability**: PASS. Every round writes structured trace fields for frontend and Skill distillation.
- **Human review for executable knowledge**: PASS. Research and SkillCandidate artifacts do not become approved Skills automatically.
- **Frontend readiness**: PASS. Service contracts are explicit and independent from Streamlit implementation.

## Project Structure

### Documentation (this feature)

```text
specs/001-ngs-ml-agent/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   ├── service-contracts.md
│   └── storage-contracts.md
└── tasks.md
```

### Source Code (repository root)

```text
src/
├── agent/
│   ├── main.py
│   ├── chat_shell.py
│   ├── control_center.py
│   ├── dialogue.py
│   ├── harness.py
│   ├── hooks.py
│   ├── modes.py
│   ├── prompts.py
│   ├── run_control.py
│   └── slash_commands.py
├── aide_adapter/
│   ├── routing.py
│   └── journal_bridge.py
├── data_intake/
│   ├── explorer.py
│   ├── socratic.py
│   ├── manifest.py
│   └── splitter.py
├── evaluation/
│   ├── cv.py
│   ├── metrics.py
│   └── threshold.py
├── frontend_api/
│   ├── dataset_service.py
│   ├── run_service.py
│   ├── memory_service.py
│   ├── skill_service.py
│   └── research_service.py
├── memory/
│   ├── dream.py
│   ├── episodic.py
│   ├── semantic.py
│   ├── metadata_index.py
│   └── skill_linker.py
├── tracking/
│   └── mlflow_tracker.py
├── provider/
│   ├── config.py
│   └── client.py
├── research/
│   ├── muyu_client.py
│   └── knowledge_ingest.py
├── skill_bridge/
│   ├── candidate.py
│   ├── generator.py
│   ├── darwin_adapter.py
│   ├── optimizer.py
│   └── registry.py
├── api/
│   ├── app.py
│   ├── routes.py
│   └── schemas.py
├── training/
│   ├── runner.py
│   └── scripts/
│       ├── train_sklearn.py
│       └── train_xgboost.py
└── ui/
    └── app.py

tests/
├── contract/
├── integration/
├── unit/
└── fixtures/

experiments/
├── data/
├── standardized/
├── models/
└── outputs/

db/
└── experiments.db
```

**Structure Decision**: Single Python project. `frontend_api/` is a stable service boundary for later Streamlit or web frontend work. `agent/control_center.py` owns planning and mode orchestration; deterministic modules own data standardization, evaluation, persistence, and Skill publishing.

## Phase 0: Research Decisions

See [research.md](./research.md). Key decisions:

- Use official GitHub Spec Kit layout for feature docs.
- Keep AIDE/tree-search integration behind `agent/harness.py`; do not let frontend or memory modules depend directly on AIDE internals.
- Use a configurable Anthropic-compatible provider rather than regex-based model routing as the long-term interface.
- Use local muyu-search-mcp for research ingestion; complex research follows its planning state machine.
- Treat darwin-skill as an optimization loop for SkillCandidate drafts before human review.

## Phase 1: Design & Contracts

See:

- [data-model.md](./data-model.md)
- [contracts/service-contracts.md](./contracts/service-contracts.md)
- [contracts/storage-contracts.md](./contracts/storage-contracts.md)
- [quickstart.md](./quickstart.md)

### Core Boundaries

| Boundary | Owner | Consumed By | Contract |
|----------|-------|-------------|----------|
| Conversational runtime | `agent/chat_shell.py`, `agent/slash_commands.py`, `agent/dialogue.py`, `agent/modes.py` | user, control center | ask/plan/agent turn |
| Mode capability guard | `agent/mode_guard.py` | ask/plan/agent handlers, services | deterministic allow/deny for tool calls and mutations |
| Functional harness router | `agent/slash_commands.py`, `agent/control_center.py` | explicit slash commands | forced domain function + natural-language tail |
| Data intake | `data_intake/*` | agent, frontend API, training | `DatasetManifest` |
| LLM control center | `agent/control_center.py` | CLI/UI | `RunRequest` → `RunStatus` / events |
| Deterministic evaluation | `evaluation/*`, `training/*` | harness, Skill reproduction | `EvaluationConfig`, `EvaluationResult` |
| Episodic memory | `memory/episodic.py` | frontend, Skill distillation, control center | `ExperimentRoundTrace` |
| Semantic memory | `memory/semantic.py` | exploration, research, Skill bridge | `MemoryEntry` |
| Dream memory maintenance | `memory/dream.py` | idle scheduler, memory service | memory-only dedupe/summarize/review job |
| Idle scheduler | `scheduler/idle.py`, `scheduler/lease.py` | CLI/API background loop | exclusive dream/maintenance lease |
| Memory-Skill bridge | `memory/skill_linker.py`, `skill_bridge/*` | Skill distillation, exploration | `SkillCandidate`, `ApprovedSkill` |
| Skill optimization | `skill_bridge/optimizer.py` | `/skill_opt`, Skill service | old/new Skill parallel test report |
| Safety hooks | `agent/hooks.py` | control center, training runner, CLI | command/file-write allow/deny result |
| Tracking | `tracking/mlflow_tracker.py` | training, reproduction, exploration | local params/metrics/artifact log |
| Exploration tools | `exploration_tools/*`, `aide_adapter/*` | exploration harness | bounded tool candidates with timeout/fallback |
| Frontend API | `frontend_api/*` | Streamlit/web UI | service methods in `contracts/service-contracts.md` |
| REST/SSE API | `api/*` | external frontend | HTTP endpoints + streaming events |

### LLM Control Center Rules

- Default CLI entry is an interactive LLM shell. One-shot subcommands remain supported for automation but are secondary.
- Runtime modes are first-class:
  - **ask mode**: stream normal LLM Q&A, no project tool calls, no experiment state mutation.
  - **plan mode**: read historical memory summaries and use Socratic dialogue to produce a validation plan; no file mutation, training execution, model artifacts, or Skill writes.
  - **agent mode**: after clarification and safety gates, call data intake, exploration, reproduction, validation, distillation, research, memory, and tracking modules.
- Slash commands are explicit harness selectors. `/agent /explore foo`, `/train_type1 foo`, and configured domain aliases force the matching function harness and pass `foo` as natural-language task context. This avoids hallucinated function selection.
- LLM proposes actions, directions, and clarifying questions.
- LLM must not compute or invent metrics, thresholds, or model artifact paths.
- Control center must retrieve relevant memory and Skill metadata before autonomous exploration.
- Control center must pause after each interactive validation result.
- Control center must persist every run transition and stop reason.
- Every LLM-proposed local command must pass `agent/hooks.py` before execution.
- The LLM may receive dataset schema, summary statistics, feature names, run traces, and metrics; it must not receive raw sample-level matrices unless the user explicitly approves.

### Conversational CLI Contract

The CLI must behave like a domain-specific Claude Code shell:

```text
$ uv run python -m src.agent.main
mlagent> /ask 什么是特定特异性下的灵敏度？
assistant> [streaming answer, no tools]
mlagent> /plan 用 experiments/data/demo 设计一个 AUC 特征探索方案
assistant> 我先确认：是否已有独立测试集，还是需要随机划分？
mlagent> /train_type1 用 experiments/data/demo 做特征探索，目标 AUC，最多 20 轮
assistant> 我先检查该路径下的特征矩阵和标签文件。请确认样本 ID 列是否为 sample_id？
mlagent> 是
assistant> 已生成 DatasetManifest。是否使用 8:2 随机划分测试集？
```

Rules:

- No-argument CLI starts `chat_shell`.
- `--no-interactive` or explicit subcommands may run automation-friendly one-shot commands.
- Slash command registry maps command names and aliases to runtime modes and domain actions: `/ask`, `/plan`, `/agent`, `/intake`, `/explore`, configured training aliases such as `/train_type1`, `/reproduce`, `/interact`, `/distill`, `/research`, `/skill_opt`, `/status`, `/stop`, `/help`.
- Natural language without a slash command is classified by the LLM runtime as ask, plan, or agent intent.
- Clarification questions, plan drafts, run IDs, pending approvals, and linked dataset IDs are stored in `ConversationSession`.

### Ask / Plan / Agent State Machine

```text
UserTurn
  ├── ask intent   → AskMode.stream_answer → ConversationTurn(done)
  ├── plan intent  → PlanMode.socratic_questions → ValidationPlan(draft|ready)
  └── agent intent → Safety + Clarification Gate → RunRequest → Tool/Service calls
```

Mode constraints:

- Ask mode cannot call project tools, write SQLite records except conversation history, or create artifacts.
- Plan mode can read lightweight metadata and memory summaries, but cannot launch training, write files, write model artifacts, or publish Skills.
- Agent mode can execute project functions through services only, and all local commands pass `agent/hooks.py`.
- A completed plan may be promoted to agent mode by explicit user instruction such as `/agent execute this plan`.
- `agent/mode_guard.py` is the hard boundary: each mode receives a `ModeCapabilityPolicy` that allows only named service methods and mutation types. Tests must verify forbidden calls are blocked even if the LLM proposes them.

### Functional Harness Design

Functional slash commands are configured harness entries, not hardcoded prompt guesses:

| Harness | Example Commands | Forced Domain Action |
|---------|------------------|----------------------|
| `intake` | `/intake` | inspect files and build `DatasetManifest` |
| `explore` | `/explore`, configured aliases such as `/train_type1` | feature exploration |
| `reproduce` | `/reproduce` | strict approved Skill reproduction |
| `interactive_validate` | `/interact`, `/validate` | one user-directed validation then pause |
| `distill` | `/distill` | notebook or best-run SkillCandidate generation |
| `research` | `/research` | muyu-search-mcp research ingestion |
| `skill_opt` | `/skill_opt` | optimize an approved Skill with backup and old/new comparison |

The LLM can fill missing parameters inside the selected harness, but the selected harness itself is fixed by the command.

Harness source of truth:

- Default harnesses are seeded from `config/harnesses.toml`.
- SQLite table `functional_harnesses` stores the active audited registry used by CLI and API.
- Alias updates must be explicit configuration changes or admin service calls, not prompt-only behavior.
- Each harness declares required inputs, whether a `ValidationPlan` can be promoted into it, and the service action it invokes.

### AIDE Exploration Tool Position

AIDE is not the global agent brain. In agent-mode exploration, the LLM control center may choose among exploration tools:

- `aide_tree_search`: AIDE-backed tree search behind `aide_adapter`.
- `memory_guided_search`: use prior successful/failed directions.
- `manual_validation_plan`: execute a ready `ValidationPlan`.
- `skill_seeded_search`: start from approved Skill parameters and explore around them.

This is feasible if AIDE is wrapped as a bounded `ExplorationTool` with explicit inputs, outputs, timeouts, and trace writing. It should not directly own conversation state, frontend state, memory mutation, or safety decisions.

`ExplorationTool` contract:

- input: dataset summary, objective metric, current best trace, run-control budget, memory/Skill context IDs, and optional user plan;
- output: proposed direction, preprocessing plan, feature subset plan, model family, rationale summary, and trace payload;
- failure: timeout, unavailable, invalid proposal, or safety rejected;
- fallback: control center retries with the next ranked tool candidate without losing the round audit trail.

### Frontend API Design

The Python service contracts remain the internal boundary. A REST/SSE layer exposes them to frontends:

- REST for commands and state queries.
- SSE or WebSocket for ask streaming, plan clarification, run progress, and round trace updates.
- All API responses use IDs from SQLite: `session_id`, `dataset_id`, `experiment_id`, `round_id`, `plan_id`, `candidate_id`, `skill_id`, `dream_job_id`.
- Frontend never talks to AIDE, MLflow, ChromaDB, or local files directly.

### Memory-Experience-Skill Bridge

The bridge is explicit:

```text
ExperimentRoundTrace → EpisodicMemory
ExperimentRoundTrace summary → SemanticMemory
SemanticMemory + trace evidence → SkillCandidate
SkillCandidate → skill-creator validation → darwin-skill iteration → human approval
ApprovedSkill execution → EpisodicMemory + SemanticMemory + SkillRegistry
```

Memory retrieval and writeback are separate contracts:

- `EpisodicMemory` is the audit log and frontend trace source.
- `SemanticMemory` is the retrieval layer for experience, project research, and method notes.
- `MetadataIndex` owns critical metadata and avoids relying on vector-store metadata behavior.
- `MemoryService` is the only frontend-facing memory interface.

### Dream Memory Maintenance

Dream jobs run only when:

- no user instruction has arrived for more than 2 hours;
- no active run is `running`;
- no Skill optimization job is running.
- the idle scheduler can acquire an exclusive lease for the current workspace.

Dream job scope:

- deduplicate memory entries;
- merge semantically equivalent notes;
- summarize repeated experiment patterns;
- mark contradictions or stale memory as `needs_review`;
- produce a dream report.

Dream job exclusions:

- never edits approved Skills;
- never changes model artifacts;
- never deletes raw experiment traces.

Scheduler rules:

- CLI and API processes may both host a background tick, but only the process holding `idle_scheduler_leases` may start a dream job.
- Leases expire automatically after a bounded TTL and must record owner, acquired time, and heartbeat time.
- A failed or expired lease never authorizes deletion of raw memory; the next job must resume from auditable state.

### Skill Self-Iteration

`/skill_opt <skill>` runs a controlled optimization workflow:

1. Back up the currently approved Skill.
2. Use darwin-skill-style evaluation and improvement to propose a candidate version.
3. Run old and candidate Skills in parallel on the same fixture or user-approved dataset.
4. Compare runtime speed, multi-run consistency, and modeling performance.
5. Produce a review report.
6. Wait for user approval before replacing the approved Skill.

Leakage and budget rules:

- The user or fixture metadata must approve the dataset used for optimization.
- Candidate selection uses training k-fold metrics only.
- Independent test metrics may be computed only after candidate selection and only for the comparison report.
- Each optimization declares repeat count, max runtime, metric, target specificity if needed, and stop reason.

### Tracking and Artifact Rules

- MLflow is used as local structured tracking only: params, metrics, tags, and artifacts.
- SQLite remains the source of truth for UI status and run traces.
- Model files are written under `experiments/models/<experiment_id>/`.
- Failed, timeout, and stopped rounds still write trace records and do not block later diagnosis.

### Frontend Interface Readiness

Frontend must never read raw AIDE state. It reads:

- Dataset manifests
- Run status and round traces
- Metric curves and stop reasons
- Memory search results
- Skill registry and SkillCandidate review state
- Research job status and knowledge entries

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
-----------|------------|-------------------------------------|
| Multiple persistence layers | SQLite facts plus semantic memory and Skill files serve different retrieval/use cases | Pure SQLite cannot provide semantic retrieval; pure vector memory cannot preserve deterministic audit traces |
| Service boundary before frontend exists | Later frontend must not couple to internals | Direct Streamlit-to-SQLite coupling would make UI replacement and testing brittle |
| SkillCandidate workflow | Executable Skills can damage reproducibility if published automatically | Direct notebook-to-Skill publication risks bad or unvalidated procedures |
