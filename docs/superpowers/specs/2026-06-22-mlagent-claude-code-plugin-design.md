# MLagent Claude Code Plugin Design

Date: 2026-06-22

## 1. System Positioning

MLagent is not a machine learning training framework, parameter optimizer, or fixed modeling method library. It is a project-level machine learning modeling memory system and prompt orchestration plugin for Claude Code.

The system relies on Claude Code for code understanding, experiment implementation, long-running exploration loops, training code changes, and retraining execution. MLagent focuses on project memory management, on-demand context assembly, raw exploration recording, experience distillation, knowledge indexing, and human-reviewed SkillVersion management for reproducible retraining.

Out of scope for the MVP:

- Built-in generic model training framework.
- Built-in hyperparameter optimization engine.
- Mandatory MLflow, DVC, Optuna, vector database, or workflow orchestrator.
- Automatic formal SkillVersion creation without human review.
- Loading all project memory into Claude Code at once.
- Team collaboration, remote GPU orchestration, or server-side platform features.

## 2. Architecture

MLagent uses a two-layer architecture.

```text
Claude Code Plugin
  ├─ skills/
  │  ├─ start-modeling-session
  │  ├─ explore-optimization
  │  ├─ retrain-from-memory
  │  ├─ distill-run-to-memory
  │  └─ promote-memory-to-skill
  ├─ hooks/
  │  ├─ session-start
  │  ├─ post-tool-use
  │  ├─ post-tool-batch
  │  └─ stop
  ├─ bin/mlagent-memory
  └─ optional MCP

Project Memory Repo
  ├─ project_profile/
  ├─ data_understanding/
  ├─ project_knowledge/
  ├─ raw_memory/
  ├─ experience/
  ├─ skill_versions/
  └─ indexes/
```

The Claude Code Plugin is installed once and provides workflow skills, hooks, and a lightweight CLI entrypoint. It guides Claude Code, assembles memory context, writes records, and calls deterministic memory operations.

Each modeling project owns an independent Project Memory Repo. The repo is stored with the project and can migrate with it. All durable assets use human-readable Markdown, YAML, or original imported files. `indexes/` contains only rebuildable SQLite FTS5 indexes.

MCP is a second-stage option. The MVP uses `bin/mlagent-memory` as the stable interface for deterministic operations.

### 2.1 Technology Stack and Reuse Map

The MVP uses a file-first architecture with a small Python toolchain. Durable assets stay in Markdown, YAML, and copied source files. Databases and indexes are accelerators only.

Research references:

- [MLagent reuse survey](../../superpowers/reports/2026-06-22-mlagent-reuse-survey.md)
- [M1 agent memory systems](../../research/2026-06-22-m1-agent-memory-systems.md)
- [M2 knowledge ingestion](../../research/2026-06-22-m2-knowledge-ingestion.md)
- [M3 SQLite FTS5 index](../../research/2026-06-22-m3-sqlite-fts5-index.md)
- [M4 Claude Code plugin](../../research/2026-06-22-m4-claude-code-plugin.md)
- [M5 context packs](../../research/2026-06-22-m5-context-packs.md)
- [M6 SkillVersion registry](../../research/2026-06-22-m6-skillversion-registry.md)

| Function | MVP technology | Reusable projects | Reuse mode |
|---|---|---|---|
| Claude Code plugin shell | Official plugin layout with `.claude-plugin/plugin.json`, `skills/`, `hooks/hooks.json`, `bin/` | `obra/superpowers`, Anthropic official plugin examples | Fork or closely copy the skeleton and hook patterns |
| CLI | Python, Typer, Pydantic v2, PyYAML or ruamel.yaml | `tiangolo/typer`, `pydantic` | Runtime dependency |
| YAML schema validation | Pydantic models over loaded YAML dictionaries | Pydantic v2 | Runtime dependency |
| Knowledge import | `pypdf` for basic PDF, direct text read for TXT/MD/YAML, optional `markdownify` for HTML | `py-pdf/pypdf`, `langchain-text-splitters`, `markdownify` | Runtime dependency for narrow subcomponents |
| Text chunking | Recursive and Markdown-aware chunking | `langchain-text-splitters` | Runtime dependency, not full LangChain |
| Search index | SQLite FTS5 through `sqlite-utils`, with standard-library `sqlite3` detection and fallback | `simonw/sqlite-utils`, SQLite FTS5 | Runtime dependency plus standard-library fallback |
| Three-layer memory model | Self-owned YAML schemas | `langmem`, `A-MEM`, `Graphiti` | Borrow data-model ideas only |
| Experience distillation | Claude Code / LLM-guided summarization into schema-checked YAML | `langmem` memory-manager pattern | Borrow prompt and schema pattern only |
| Context Pack assembly | Custom pack generator with fixed MLagent priority tables | `anthropics/skills`, `Agent-Skills-for-Context-Engineering`, `obra/superpowers` | Borrow progressive loading and filesystem-context rules |
| SkillVersion registry | File-backed version registry with human approval state | `iterative/mlem`, `operatorai/modelstore`, Git PR review pattern | Borrow schema and lifecycle ideas only |
| Optional second-stage MCP | Python MCP SDK FastMCP | `modelcontextprotocol/python-sdk` | Deferred, not MVP |

The MVP should not import full memory runtimes or RAG frameworks. `mem0`, `letta`, `cognee`, `graphiti`, LangChain, LlamaIndex, Unstructured, MLflow, DVC, Optuna, and workflow orchestrators are reference material only unless a later phase explicitly changes scope.

### 2.2 Dependency Policy

Default runtime dependencies should stay small and local:

```text
typer
pydantic
pyyaml or ruamel.yaml
pypdf
langchain-text-splitters
sqlite-utils
markdownify optional
```

The MVP must avoid dependencies that require GPU stacks, persistent services, vector databases, or heavyweight PDF/OCR pipelines. In particular, do not default to PyMuPDF because of AGPL distribution risk, Marker because of torch and GPL weight, Docling standard mode because it pulls heavy ML dependencies, or any vector database.

## 3. Project Memory Structure

```text
project_memory/
  ├─ project_profile/
  ├─ data_understanding/
  ├─ project_knowledge/
  ├─ raw_memory/
  ├─ experience/
  ├─ skill_versions/
  └─ indexes/
```

### 3.1 project_profile

```text
project_profile/
  ├─ project.yaml
  └─ objectives.md
```

This records project identity, task type, active modeling objectives, primary metrics, data entrypoints, and memory repo version.

### 3.2 data_understanding

```text
data_understanding/
  ├─ dataset_card.md
  ├─ schema.yaml
  ├─ label_definition.md
  └─ data_versions.yaml
```

This is shared by exploration and retraining. It records field semantics, label definitions, sample sources, data structure, data versions, and known data quality issues.

### 3.3 project_knowledge

```text
project_knowledge/
  ├─ docs/
  ├─ papers/
  ├─ notes/
  ├─ originals/
  └─ registry.yaml
```

The system allows direct import of project documents and papers. Imported files are copied into `project_knowledge/originals/` by default, then text is extracted, summarized, chunked, and indexed. Project knowledge provides exploration reference material; it is not treated as verified project experience.

### 3.4 raw_memory

```text
raw_memory/
  ├─ sessions/
  ├─ explorations/
  ├─ runs/
  └─ human_notes/
```

`raw_memory` is the evidence layer and uses standard-granularity recording. It stores exploration goals, hypotheses, attempted directions, file-change summaries, key command summaries, run results, metric changes, failure causes, human interventions, and evidence paths.

It prioritizes faithful process recording over polished conclusions. It is the source material for experience distillation and candidate SkillVersion generation.

### 3.5 experience

```text
experience/
  ├─ lessons/
  ├─ pitfalls/
  ├─ successful_patterns/
  └─ failed_directions/
```

`experience` is distilled from `raw_memory` and serves future exploration. It can be automatically inserted, but every entry must include source references, confidence, and review state.

Experience improves exploration by preserving useful lessons, repeated pitfalls, successful patterns, failed directions, and optimization hints. It is not a strict retraining procedure and cannot directly become a formal SkillVersion.

### 3.6 skill_versions

```text
skill_versions/
  ├─ registry.yaml
  └─ v001_*/
      ├─ skill.yaml
      ├─ reproduce.md
      ├─ constraints.md
      ├─ validation_checklist.md
      ├─ performance.yaml
      └─ source_evidence.yaml
```

`skill_versions` stores strict retraining assets. A formal SkillVersion can only be created after human review confirms that the training result and benchmark performance meet requirements.

There are only two valid source paths:

1. A best exploration workflow that reached or exceeded the target and passed human performance review.
2. A human-created training notebook that passed human performance and reproducibility review.

Claude Code may generate a candidate SkillVersion draft, but it must not formally insert a SkillVersion without explicit human approval and recorded performance details.

### 3.7 indexes

```text
indexes/
  └─ memory.sqlite
```

The MVP uses SQLite FTS5 as the default index. `sqlite-utils` is the preferred wrapper because it supports FTS enablement, upsert by primary key, and rebuild operations. The standard-library `sqlite3` module should be used to detect FTS5 availability and can serve as a fallback implementation.

Indexes are rebuildable and never serve as the sole source of any durable asset.

## 4. On-Demand Loading and Context Packs

Core loading principle:

```text
Current goal drives retrieval; summaries load first; full cards load on demand; evidence loads last.
```

MLagent uses four loading levels:

```text
L0 Memory Manifest
  Project identity, asset directories, update timestamps, available SkillVersion list.

L1 Context Pack
  Minimal task-specific context generated from the current prompt.

L2 Memory Card
  Full content for a selected experience, data note, knowledge item, or skill version.

L3 Evidence
  Raw records, notebooks, metrics, code paths, and artifacts loaded only for review,
  tracing, or SkillVersion approval.
```

### 4.1 Exploration Context Pack

Retrieval priority is fixed:

1. Current input prompt: direction, plan, target, and constraints.
2. `data_understanding`: current data, labels, fields, sample structure.
3. `experience`: relevant high or medium confidence lessons and pitfalls.
4. `project_knowledge`: relevant project documents and literature snippets.
5. `skill_versions`: available versions as reference only, not mandatory procedures.

Exploration should not load full `raw_memory` by default. Low-confidence experience may be surfaced only with an explicit caution.

### 4.2 Retraining Context Pack

Retraining is centered on one specified SkillVersion:

1. Full specified SkillVersion.
2. Relevant `data_understanding`.
3. Strict reproduction constraints.
4. Validation checklist.
5. Output registration rules.

Retraining must not freely absorb exploration advice unless the user explicitly asks to both retrain and optimize.

### 4.3 Experience Distillation Context Pack

Experience distillation uses:

1. Current-session `raw_memory`.
2. Related historical `experience`.
3. Human notes.
4. Project goals and data background.

The output is inserted into `experience/` with confidence, review state, and source references.

### 4.4 SkillVersion Candidate Context Pack

SkillVersion candidate generation uses:

1. Best exploration workflow or notebook source.
2. Related `raw_memory` and evidence.
3. Code paths, metric files, and data versions.
4. Human review requirements.

The output is only a candidate. Formal insertion requires human review and performance recording.

## 5. Core Workflows

### 5.1 start-modeling-session

```text
Select Project Memory Repo
-> Read project_profile
-> Read L0 Memory Manifest
-> Receive current goal prompt
-> Generate minimal startup Context Pack
-> Create raw_memory/sessions record
```

Outputs include session ID, project objective summary, and available memory assets.

### 5.2 explore-optimization

```text
Current prompt
-> Retrieve data_understanding, experience, project_knowledge, and skill_versions list
-> Generate exploration plan
-> Claude Code reads code, edits code, runs experiments, and analyzes results
-> hooks/CLI write raw_memory records
-> Update explorations and runs
-> Generate end-of-run summary
```

MLagent does not implement the training method. Claude Code performs the exploration through project code and user goals.

### 5.3 distill-run-to-memory

```text
Read current raw_memory
-> Extract lessons, pitfalls, successful patterns, and failed directions
-> Write experience entries
-> Attach confidence, needs_review, and source_raw_records
-> Rebuild or update SQLite FTS5 index
```

Experience is automatically inserted but remains confidence-scored.

### 5.4 promote-memory-to-skill

```text
Human specifies best run or best exploration
-> Gather raw_memory, metrics, code paths, and data versions
-> Generate candidate SkillVersion
-> Human reviews training results and benchmark performance
-> If approved, write skill_versions/vXXX
-> Record version in registry.yaml
-> Record performance details in performance.yaml
```

No human review means no formal SkillVersion.

### 5.5 import-notebook-as-skill

```text
Copy or register the notebook as evidence
-> Extract workflow, dependencies, inputs, outputs, metrics, and key code blocks
-> Generate candidate SkillVersion
-> Human reviews performance and reproducibility
-> If approved, write skill_versions/vXXX
```

This path also requires human review and performance recording.

### 5.6 retrain-from-memory

```text
User specifies SkillVersion and new data
-> Load full SkillVersion
-> Load relevant data_understanding
-> Claude Code follows reproduce.md and constraints.md strictly
-> Run validation_checklist
-> Write raw_memory/runs
-> Record new artifacts and performance
```

Retraining results do not automatically mutate the SkillVersion. A better result must go through the promotion workflow.

## 6. CLI and Hooks

### 6.1 CLI

The MVP exposes deterministic operations through `bin/mlagent-memory`.

```text
mlagent-memory init
mlagent-memory status
mlagent-memory index
mlagent-memory import-knowledge
mlagent-memory add-raw
mlagent-memory search
mlagent-memory create-context-pack
mlagent-memory add-experience
mlagent-memory create-skill-candidate
mlagent-memory approve-skill
mlagent-memory list-skills
mlagent-memory get-skill
```

Responsibilities:

- `init`: create standard memory directories and templates.
- `status`: report memory repo state, asset counts, and recent updates.
- `index`: rebuild SQLite FTS5 from durable assets.
- `import-knowledge`: copy documents into `project_knowledge/originals/`, extract text, summarize, and index.
- `add-raw`: write raw memory records.
- `search`: retrieve memory assets by keyword and type.
- `create-context-pack`: generate exploration, retraining, distillation, or skill-candidate context.
- `add-experience`: write distilled experience entries.
- `create-skill-candidate`: create candidate SkillVersion drafts.
- `approve-skill`: formalize a candidate after human review and performance confirmation.
- `list-skills` and `get-skill`: support strict retraining.

### 6.2 Hooks

Hooks should be conservative. Plugin hooks must live in `hooks/hooks.json`, aligned with the Claude Code plugin layout. The MVP starts with command hooks; more advanced prompt or agent hooks are not required.

```text
session-start
  -> Remind the user to select a Project Memory Repo
  -> Show memory status
  -> Do not load large content automatically

post-tool-use
  -> Capture key command summaries, file-change summaries, and result signals
  -> Write raw_memory drafts
  -> Do not store full logs unless explicitly requested

post-tool-batch
  -> Prefer one batch summary when many tool calls happen together
  -> Reduce noise compared with one record per low-value tool event

stop
  -> Generate session summary
  -> Generate candidate experience entries
  -> Call add-experience for automatic insertion
```

Safety rules:

- Hooks record summaries and paths by default, not full logs, full diffs, training data copies, or model binaries.
- `approve-skill` requires explicit human confirmation.
- Formal SkillVersion insertion requires `performance.yaml`.
- `indexes/` cannot contain the only copy of any asset.
- Knowledge import copies source files by default and records hash and source path.
- `SessionStart` output must stay small and should use additional context only for status, manifest, and routing hints.

## 7. Data Schemas

YAML and Markdown are used together:

```text
Markdown is for human reading.
YAML is for validation, retrieval, and automation.
```

CLI validation should use Pydantic or an equivalent schema layer.

Typer does not replace Pydantic. Typer handles CLI parsing; Pydantic validates YAML data after loading it into dictionaries.

### 7.1 Raw Memory

```yaml
id: raw_20260622_001
type: session | exploration | run | human_note
created_at: "2026-06-22T10:00:00+08:00"
session_id: session_20260622_001
goal: "Exploration goal"
hypothesis: "Current hypothesis"
actions:
  - "Attempted direction or key operation"
changed_files:
  - path: "train.py"
    summary: "Changed feature selection logic"
commands:
  - command: "python train.py --config ..."
    summary: "Executed training"
    status: success | failed
results:
  metrics:
    auc: 0.91
    f1: 0.83
  artifacts:
    - "outputs/model.pkl"
failure_reason: null
human_interventions:
  - "User required retaining a specific feature"
evidence_links:
  - "runs/run_001/metrics.json"
next_steps:
  - "Validate on external test set"
```

### 7.2 Experience

```yaml
id: exp_20260622_001
type: lesson | pitfall | successful_pattern | failed_direction
object_type: experience
summary: "Short summary"
detail: "Full experience description"
confidence: low | medium | high
needs_review: true | false
source_raw_records:
  - "raw_memory/runs/raw_20260622_001.yaml"
applies_when:
  - "sample size < 500"
avoid_when:
  - "external validation unavailable"
related_data_fields:
  - "age"
related_methods:
  - "xgboost"
related:
  - "exp_20260621_003"
valid_from: "2026-06-22T10:30:00+08:00"
superseded_by: null
created_at: "2026-06-22T10:30:00+08:00"
```

The experience schema borrows three ideas without importing their runtimes: LangMem-style episodic fields, A-MEM-style atomic cards and related links, and Graphiti-style temporal validity.

### 7.3 Knowledge Registry

```yaml
id: know_20260622_001
type: project_doc | paper | method_note | data_doc
title: "Document title"
original_filename: "paper.pdf"
stored_path: "project_knowledge/originals/paper.pdf"
source_path: "/old/path/paper.pdf"
sha256: "..."
imported_at: "2026-06-22T10:40:00+08:00"
summary: "Summary"
tags:
  - "feature_selection"
index_status: indexed
```

### 7.4 SkillVersion

```yaml
version: "v001"
name: "xgboost_baseline_retrain"
object_type: skill_version
state: approved
source_type: best_run | ipynb_import
source_evidence:
  - "raw_memory/runs/raw_20260622_001.yaml"
  - "evidence/notebooks/baseline.ipynb"
artifacts:
  - path: "skill_versions/v001_xgboost_baseline_retrain/reproduce.md"
    sha256: "..."
requirements:
  python: ">=3.10"
  packages:
    - "scikit-learn==..."
human_review:
  reviewed: true
  reviewer: "Reviewer name"
  reviewed_at: "2026-06-22T11:00:00+08:00"
  approval_note: "Performance meets target; usable as retraining procedure"
performance:
  primary_metric:
    name: "auc"
    value: 0.91
  benchmark_metric:
    name: "baseline_auc"
    value: 0.86
  dataset_version: "data_v003"
  validation_protocol: "5-fold CV + holdout"
reproducibility:
  entrypoint: "train.py"
  required_inputs:
    - "data/train.csv"
  expected_outputs:
    - "outputs/model.pkl"
  locked_steps:
    - "feature engineering workflow"
    - "model type"
  allowed_changes:
    - "new sample path"
    - "output directory"
valid_from: "2026-06-22T11:00:00+08:00"
superseded_by: null
```

The SkillVersion schema borrows MLEM's `object_type`, `artifacts`, `requirements`, and free-extension pattern; modelstore's lifecycle-state idea; and Graphiti's temporal versioning idea. It remains an MLagent-owned YAML schema.

## 8. Insertion Rules

- `raw_memory`: can be written automatically by hooks or CLI.
- `experience`: can be automatically distilled and inserted, but must include confidence, review state, and source records.
- `project_knowledge`: import copies the original file by default, extracts text, and indexes it.
- `skill_versions`: can only be formally inserted by `approve-skill` after human review confirms benchmark performance.
- `indexes`: generated by CLI only and never serve as durable asset source.
- SkillVersion states are `draft`, `pending_review`, `approved`, `rejected`, and `archived`.
- The MVP must not build a custom approval service. Local explicit CLI approval is sufficient for single-machine use; when the project is managed through hosted Git, Git PR review is the preferred approval gate and audit trail.

## 9. MVP Scope

The MVP must include:

1. `project_memory/` initialization.
2. Knowledge import and SQLite FTS5 indexing for Markdown, TXT, and basic PDF extraction.
3. Standard raw memory recording for session, exploration, run, and human note records.
4. Automatic experience distillation with confidence and source references.
5. Exploration and retraining Context Pack generation.
6. SkillVersion candidate creation from best run and notebook import.
7. Human-reviewed SkillVersion approval with performance details.
8. `list-skills` and `get-skill` for strict retraining.
9. Claude Code Plugin skills and conservative hooks.

The MVP does not include:

- A training framework.
- A parameter optimizer.
- Default vector database integration.
- Default MCP server integration.
- Team collaboration or remote training.
- Automatic formal SkillVersion creation.
- Full log, full diff, or full training-data capture by default.

## 10. Acceptance Criteria

The MVP is acceptable when it supports these end-to-end flows.

### 10.1 Exploration Flow

```text
User enters exploration goal
-> System creates exploration Context Pack
-> Claude Code explores through project code
-> raw_memory records process summaries
-> experience is automatically distilled and inserted
```

### 10.2 Notebook to SkillVersion Flow

```text
Import ipynb
-> Generate candidate SkillVersion
-> Human fills or confirms performance details
-> approve-skill
-> skill_versions/vXXX is formally inserted
```

### 10.3 Fast Retraining Flow

```text
User specifies SkillVersion and new data
-> System creates retraining Context Pack
-> Claude Code strictly follows SkillVersion
-> New run and performance are recorded
```

Core success statement:

```text
Across multiple Claude Code exploration sessions in one project, raw_memory accumulates;
raw_memory can be distilled into experience;
human-confirmed best workflows or notebooks can become SkillVersions;
new samples can be retrained through a specified SkillVersion;
all assets remain readable, portable, indexable, and traceable.
```
