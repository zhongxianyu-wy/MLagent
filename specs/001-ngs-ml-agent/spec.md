# Feature Specification: NGS ML Experiment Agent

**Feature Branch**: `001-ngs-ml-agent`

**Created**: 2026-05-25

**Status**: Draft - ready for plan/task execution review

**Input**: User description: "Build a local NGS machine-learning experiment agent that understands user-provided feature matrices and labels, explores feature engineering directions, reproduces approved Skills, supports interactive validation, distills Skills, ingests literature/project knowledge, and preserves memory/experience for future runs."

## User Scenarios & Testing *(mandatory)*

### User Story 0 - Conversational LLM Runtime (Priority: P1)

As a user, I enter a Claude Code-like interactive CLI where I can ask questions, build a validation plan through Socratic dialogue, or run agentic actions. I can chat naturally or invoke slash commands such as `/ask`, `/plan`, `/agent`, `/intake`, `/explore`, `/reproduce`, `/interact`, `/distill`, `/research`, or project-specific aliases like `/train_type1`. The LLM runtime should route the turn to ask, plan, or agent mode, stream responses when only answering, ask follow-up questions when planning, execute tools only in agent mode, and continue the conversation.

**Why this priority**: The product is meant to be entered through an LLM question-answer loop, not primarily through one-shot argparse commands.

**Independent Test**: Start the CLI with no subcommand. Submit `/ask 什么是特定特异性下的灵敏度`, submit `/plan 用 experiments/data/demo 设计一个 AUC 探索方案`, then submit `/agent /train_type1 用 experiments/data/demo 做特征探索，目标 AUC`. The shell streams the ask answer, conducts Socratic planning without executing, then routes the agent command to execution with session state preserved.

**Acceptance Scenarios**:

1. **Given** the user runs the CLI without arguments, **When** the process starts, **Then** it opens an interactive LLM shell instead of printing only argparse help.
2. **Given** the user types `/ask ...`, **When** the turn is handled, **Then** the system streams a normal LLM answer and does not call project tools or mutate experiment state.
3. **Given** the user types `/plan ...`, **When** the plan lacks details, **Then** the system may read historical memory summaries and asks Socratic clarification questions, then produces a validation plan without modifying files, launching training, or writing model artifacts.
4. **Given** a validation plan is ready, **When** the user confirms execution with `/agent execute current plan`, **Then** the system converts the plan into an executable agent run.
5. **Given** the user types an explicit functional slash command such as `/explore ...` or a configured alias such as `/train_type1 ...`, **When** the command is parsed in agent mode, **Then** the command router must force the corresponding function harness and pass the remaining natural-language text as context, bypassing broad intent guessing for the function selection.
6. **Given** the user's natural-language request lacks required information, **When** the control center cannot start safely, **Then** it asks one Socratic follow-up question and waits for the answer.
7. **Given** a run finishes or pauses, **When** the result is returned, **Then** the shell remains in conversation and accepts follow-up natural-language instructions.

---

### User Story 1 - Standardize Input Data (Priority: P1)

As a bioinformatics engineer, I provide a path containing one or more manually prepared feature matrices, grouping labels, and optional train/test files. The agent should inspect the files, ask Socratic clarification questions only when needed, and produce a standard dataset manifest for downstream training.

**Why this priority**: Every downstream training, reproduction, memory, and UI feature depends on a reliable standard input contract.

**Independent Test**: Provide a directory with a feature CSV and separate labels CSV. The agent identifies candidate files, asks for any missing label/split clarification, and writes a standard manifest plus standardized train/test files.

**Acceptance Scenarios**:

1. **Given** a directory with feature and label files, **When** the user starts data standardization, **Then** the system creates a `DatasetManifest` with feature paths, label paths, sample ID column, label column, positive/negative labels, split strategy, and notes.
2. **Given** no independent test set, **When** the user confirms a split ratio, **Then** the system creates a reproducible train/test split with a fixed random seed.
3. **Given** ambiguous files or columns, **When** auto-detection confidence is low, **Then** the system asks one Socratic question at a time and persists the user's answers.

---

### User Story 2 - Explore Feature Engineering Directions (Priority: P1)

As a bioinformatics engineer, I run feature exploration on the standardized dataset. If I do not specify a direction, the agent should consult the memory and Skill systems, pick unfinished or promising directions, and prioritize feature engineering.

**Why this priority**: The product's primary value is reducing repeated manual feature engineering work.

**Independent Test**: Run a 10-round exploration on a small fixture dataset and verify each round records direction, preprocessing, feature subset strategy, k-fold metrics, threshold policy, stop reason, and best configuration.

**Acceptance Scenarios**:

1. **Given** a standardized dataset and no user-specified direction, **When** exploration starts, **Then** the agent retrieves relevant memory and Skill metadata before proposing the first direction.
2. **Given** feature exploration is running, **When** each round completes, **Then** the system stores a structured trace with preprocessing, feature subset selection, model, metrics, threshold, and LLM rationale.
3. **Given** target performance, maximum iterations, runtime limit, and patience are configured, **When** any stop condition is met, **Then** the run stops and records the stop reason.

---

### User Story 3 - Reproduce a Skill Strictly (Priority: P2)

As a user, I select an approved Skill from the Skill library and ask the system to reproduce it on the current dataset. The system should follow the Skill exactly, only adapting file paths, column names, and label mappings when allowed.

**Why this priority**: Approved experimental paradigms must be reusable without re-inventing the training logic.

**Independent Test**: Select a fixture Skill and dataset. The run executes the Skill workflow, logs k-fold and optional test metrics, saves the model artifact, and records the Skill execution in memory.

**Acceptance Scenarios**:

1. **Given** an approved Skill and standardized dataset, **When** reproduction starts with strict mode, **Then** the system executes the Skill's preprocessing, feature selection, model, and evaluation steps without exploratory changes.
2. **Given** the Skill references expected input fields, **When** dataset column names differ, **Then** only declared dataset adaptation is allowed.
3. **Given** reproduction completes, **When** results are written, **Then** the system stores model artifact path, metrics, Skill ID, and applicability notes.

---

### User Story 4 - Interactively Validate User Directions (Priority: P2)

As a researcher, I provide a hypothesis or validation direction in natural language. The agent should run the requested experiment, return results, and wait for the next instruction instead of continuing autonomously.

**Why this priority**: PI and senior researcher workflows require controlled scientific iteration rather than fully autonomous search.

**Independent Test**: Ask the agent to test one feature transformation or subset strategy. It runs the experiment, records results, returns metrics and interpretation, then pauses for the next instruction.

**Acceptance Scenarios**:

1. **Given** a user-provided validation direction, **When** the agent executes it, **Then** the result includes k-fold metrics, threshold basis, optional test metrics, and a concise interpretation.
2. **Given** the result is returned, **When** no next instruction is supplied, **Then** the run remains paused and does not start a new direction.

---

### User Story 5 - Distill Skills from Notebooks or Runs (Priority: P3)

As a user, I trigger Skill distillation from either a specified `.ipynb` file or the best current exploration/interactive run. The system should create a SkillCandidate, validate it against `skill-creator` rules, iterate it with darwin-skill, and require human approval before publishing.

**Why this priority**: Reusable Skills are how local experience becomes executable team knowledge.

**Independent Test**: Provide a notebook or best run trace. The system creates a draft SkillCandidate, validates required frontmatter and resource structure, runs an evaluation/improvement loop, and leaves it pending human review.

**Acceptance Scenarios**:

1. **Given** a notebook with method code and conclusion markdown, **When** Skill distillation starts, **Then** the system creates a SkillCandidate with standard `SKILL.md` frontmatter and concise procedural steps.
2. **Given** a best run trace, **When** distillation starts, **Then** the system summarizes the preprocessing, feature subset selection, model, evaluation, and applicability constraints into a SkillCandidate.
3. **Given** a SkillCandidate, **When** validation and darwin-skill iteration complete, **Then** the candidate is not published until a human approves it.

---

### User Story 6 - Ingest Literature and Project Knowledge (Priority: P3)

As a researcher, I specify a paper, repository, or automatic research goal. The agent should use the local muyu-search-mcp workflow to study methods and code, then store structured knowledge in semantic memory without automatically publishing a Skill.

**Why this priority**: External methods should enrich memory before becoming executable Skills.

**Independent Test**: Provide a paper URL or GitHub project. The system performs planned research, extracts method principles and reference code, stores knowledge entries with source metadata, and makes them searchable.

**Acceptance Scenarios**:

1. **Given** a target paper or repository, **When** research starts, **Then** the system extracts method principle, feature engineering, model, evaluation, code references, applicability, and limitations.
2. **Given** automatic research mode, **When** launched, **Then** the system searches recent machine-learning feature engineering/model methods and stores summarized knowledge with source dates.
3. **Given** a research result, **When** ingestion completes, **Then** it enters semantic memory as knowledge and can only become a SkillCandidate after validation or human confirmation.

## Edge Cases

- Feature matrix orientation is transposed: system must detect or ask whether samples are rows or columns.
- Sample IDs differ between feature and label files: system must report unmatched IDs and require confirmation before dropping or imputing.
- Labels are multiclass: MVP supports binary classification; system must ask whether to select one-vs-rest or reject for this run.
- Test set exists but lacks labels: system may score later but cannot use it as guidance metric.
- k-fold is larger than the minority class count: system must reduce `k` with confirmation or stop with a clear error.
- A Skill requests a feature absent from the current dataset: strict reproduction must fail unless the Skill declares an adaptation rule.
- Research tool cannot access a source: system must store a failed-source note and continue with available sources.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST inspect one or more user-specified paths and identify candidate feature, label, split, notebook, paper, or project files.
- **FR-002**: System MUST use Socratic clarification for ambiguous data intake decisions, asking one blocking question at a time.
- **FR-003**: System MUST produce a `DatasetManifest` before any training run.
- **FR-004**: System MUST support exploration, strict Skill reproduction, interactive validation, Skill distillation, and research ingestion modes.
- **FR-005**: Feature exploration MUST prioritize preprocessing before feature subset selection, and feature subset selection before model/hyperparameter optimization.
- **FR-006**: Feature subset selection MUST include filtering methods such as low variance, correlation, statistical tests, model importance, recursive selection, and stability selection as candidate strategies.
- **FR-007**: All training MUST use configurable k-fold evaluation on the training set.
- **FR-008**: Threshold selection MUST be based on concatenated validation-fold predictions from training k-folds, never on test-set predictions.
- **FR-009**: Guidance metrics MUST support AUC, accuracy, and sensitivity at target specificity.
- **FR-010**: If an independent labeled test set exists, final guidance performance MUST use test metrics; otherwise it MUST use k-fold validation mean.
- **FR-011**: Every run MUST enforce termination conditions: target performance, maximum iterations, maximum runtime, patience/no-improvement, and user stop.
- **FR-012**: Every exploration or validation round MUST persist structured trace data for frontend display and later Skill distillation.
- **FR-013**: The memory system MUST link episodic traces, semantic knowledge, Skill candidates, and approved Skills through stable IDs.
- **FR-014**: Approved Skills MUST record their execution results back to episodic memory, semantic memory, and the Skill registry.
- **FR-015**: Skill distillation MUST follow `skill-creator` structure and validation rules.
- **FR-016**: Skill candidates MUST pass a darwin-skill style evaluate-improve-test-keep/revert loop before human approval.
- **FR-017**: Research ingestion MUST use the local `/Users/zhongxianyu/Desktop/muyu-search-mcp` workflow for web/project research.
- **FR-018**: LLM access MUST be configurable for Anthropic-compatible APIs using provider name, base URL, API key environment variable, model, small model, max tokens, and timeout.
- **FR-019**: Frontend-facing interfaces MUST expose dataset manifest, run status, round traces, memory search, Skill registry, SkillCandidate review, and research job status.
- **FR-020**: The LLM control center MUST plan and choose actions, but objective metrics, thresholds, and model artifacts MUST come from deterministic local evaluation code.
- **FR-021**: CLI entry without a subcommand MUST open an interactive LLM command shell.
- **FR-022**: The interactive shell MUST support slash commands plus natural-language descriptions, including configurable aliases such as `/train_type1`.
- **FR-023**: Slash command parsing MUST preserve the natural-language tail and pass it to the LLM control center as task context.
- **FR-024**: The shell MUST maintain conversation/session state across clarification questions, run results, and follow-up instructions.
- **FR-025**: The interactive shell MUST provide ask mode for streaming LLM Q&A without tool execution or state mutation.
- **FR-026**: The interactive shell MUST provide plan mode for Socratic validation-plan design that may read historical memory but must not modify files, execute training, or write model artifacts.
- **FR-027**: The interactive shell MUST provide agent mode for invoking project tools and functional modules after safety and clarification gates pass.
- **FR-028**: Natural-language turns without a slash command MUST be routed to ask, plan, or agent mode by the LLM runtime based on user intent and risk.
- **FR-029**: Explicit functional slash commands MUST force a configured domain harness and must not rely on free-form intent recognition to choose the function.
- **FR-030**: A ready `ValidationPlan` MUST be convertible into an agent-mode run by explicit user confirmation.
- **FR-031**: Frontend integration MUST expose REST endpoints and streaming channels for conversation turns, run status, round traces, memory search, Skill review, Skill optimization, and research jobs.
- **FR-032**: AIDE MUST be available to agent-mode exploration as one candidate exploration tool behind an adapter, not as the global control loop.
- **FR-033**: When the system has no new user instruction and no active run for more than 2 hours, it MAY start a dream job that deduplicates, summarizes, and reviews memory entries, but it MUST NOT modify approved Skills.
- **FR-034**: The `/skill_opt` command MUST optimize a target Skill through a darwin-skill-style loop, back up the old Skill before changes, run old/new versions in parallel modeling tests, compare speed, multi-run consistency, and modeling performance, then wait for user approval before replacing the approved Skill.
- **FR-035**: Storage MUST support multiple conversation sessions, datasets, runs, validation plans, dream jobs, and Skill optimization jobs with stable relationships.
- **FR-036**: Runtime mode constraints MUST be enforced by a deterministic mode guard so ask mode cannot call project tools and plan mode cannot write files, launch runs, create model artifacts, or mutate Skills.
- **FR-037**: Dream jobs MUST use an idle scheduler with an exclusive lease/lock so multiple CLI/API processes cannot start duplicate dream jobs for the same idle window.
- **FR-038**: Functional harness aliases such as `/train_type1` MUST come from an auditable registry or seed configuration rather than prompt-only intent inference.
- **FR-039**: AIDE integration MUST conform to a bounded `ExplorationTool` contract with explicit inputs, outputs, timeouts, trace writing, and fallback behavior when unavailable.
- **FR-040**: Skill optimization MUST define dataset approval, repeat count, runtime budget, comparison metric, and leakage policy; candidate selection MUST NOT use test-set predictions or labels except for final reporting.

### Key Entities

- **DatasetManifest**: Standard description of input data, labels, splits, and source files.
- **RunControlPolicy**: Target metric, iteration/runtime limits, patience, and stop criteria.
- **ExperimentRun**: A user-triggered run in exploration, reproduction, interactive, distillation, or research mode.
- **ExperimentRoundTrace**: Per-round direction, preprocessing, feature strategy, model, metrics, threshold, status, and LLM rationale.
- **EvaluationResult**: k-fold, threshold, and optional test metrics.
- **MemoryEntry**: Semantic knowledge or experience with source, confidence, and links to runs or Skills.
- **SkillCandidate**: Draft Skill awaiting validation, darwin-skill iteration, and human review.
- **ApprovedSkill**: Published reusable Skill with metadata, applicability constraints, and execution history.
- **ResearchArtifact**: Structured paper/project/method finding stored in semantic memory.
- **LLMProviderConfig**: Anthropic-compatible provider settings.
- **ConversationSession**: Interactive shell state, slash command history, linked run IDs, and pending clarification.
- **ConversationTurn**: A single ask, plan, or agent turn with raw text, parsed command, mode, streamed response, and tool-use status.
- **ValidationPlan**: A Socratic plan-mode artifact describing dataset assumptions, metric, k-fold, threshold policy, proposed exploration directions, stop conditions, and execution readiness.
- **ModeCapabilityPolicy**: Deterministic allow/deny policy for tool calls and state mutations by runtime mode.
- **FunctionalHarness**: Auditable mapping from slash commands/aliases to forced domain actions and required inputs.
- **ExplorationTool**: Bounded tool candidate interface used by the exploration harness, including AIDE-backed and memory-guided strategies.
- **DreamJob**: Idle-time memory maintenance job that deduplicates, summarizes, and reviews semantic/episodic memory without touching approved Skills.
- **IdleSchedulerLease**: Exclusive lease record preventing duplicate idle maintenance work across processes.
- **SkillOptimizationJob**: `/skill_opt` run comparing old and candidate Skill versions across speed, consistency, and performance before user approval.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: For a fixture directory with separate features and labels, the system produces a valid `DatasetManifest` after at most three clarification questions.
- **SC-002**: A 10-round exploration fixture records 10 `ExperimentRoundTrace` rows with direction, preprocessing, feature subset strategy, k-fold metrics, threshold policy, and stop status.
- **SC-003**: Threshold selection tests prove test-set labels are not used to choose thresholds.
- **SC-004**: A strict Skill reproduction fixture either completes using the declared Skill workflow or fails with an explicit missing-input/adaptation error.
- **SC-005**: A SkillCandidate generated from a notebook or best run passes required frontmatter validation and remains unpublished until human approval.
- **SC-006**: A research ingestion fixture stores at least one searchable `ResearchArtifact` with source URL/project, method summary, and applicability notes.
- **SC-007**: Ask mode streams an answer for a fixture question and records no experiment, trace, SkillCandidate, or research artifact.
- **SC-008**: Plan mode creates a `ValidationPlan` through at least one clarification question and does not execute training.
- **SC-009**: Agent mode routes `/train_type1 ...` and natural-language equivalent requests to the same exploration `RunRequest`.
- **SC-010**: Plan mode can cite historical memory summaries but leaves filesystem artifacts, training runs, and model outputs unchanged.
- **SC-011**: `/skill_opt` produces an old-vs-new Skill comparison report and does not replace the approved Skill until user approval.
- **SC-012**: Dream mode can consolidate duplicate memory entries after idle time and creates an auditable dream job record.
- **SC-013**: Mode guard tests prove ask and plan modes cannot invoke forbidden services even if the LLM proposes tool use.
- **SC-014**: Functional harness tests prove `/train_type1` is resolved from configured aliases and not free-form intent classification.
- **SC-015**: AIDE fallback tests prove exploration can continue with another tool candidate when AIDE times out or is unavailable.
- **SC-016**: Skill optimization tests prove candidate selection ignores test-set predictions and respects configured repeat/runtime budgets.

## Assumptions

- MVP is local, single-user, and focused on binary classification from already processed feature matrices.
- Raw BAM/VCF processing is out of scope for MVP.
- Streamlit or a future frontend will consume service contracts; the initial implementation may expose Python service APIs and CLI commands first.
- Tests are expected for core contracts because evaluation and memory integrity are high-risk.
