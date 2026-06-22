# MLagent Research Fit Evaluation Spec

Date: 2026-06-22

## 1. Purpose

This spec audits the research documents under `docs/research/` and `docs/superpowers/reports/` against the confirmed MLagent design.

It answers three questions:

1. Does the research fit MLagent's actual design constraints?
2. Which projects are safe to reuse directly, and which should only influence our schema or workflow?
3. What corrections or guardrails must be applied before implementation planning?

Primary design reference:

- `docs/superpowers/specs/2026-06-22-mlagent-claude-code-plugin-design.md`

Research references:

- `docs/research/README.md`
- `docs/research/2026-06-22-m1-agent-memory-systems.md`
- `docs/research/2026-06-22-m2-knowledge-ingestion.md`
- `docs/research/2026-06-22-m3-sqlite-fts5-index.md`
- `docs/research/2026-06-22-m4-claude-code-plugin.md`
- `docs/research/2026-06-22-m5-context-packs.md`
- `docs/research/2026-06-22-m6-skillversion-registry.md`
- `docs/superpowers/reports/2026-06-22-mlagent-reuse-survey.md`

## 2. Confirmed Design Constraints

The research is considered fit only if it preserves these constraints:

1. MLagent is not a model training framework or hyperparameter optimizer.
2. Claude Code remains responsible for exploration, code changes, training execution, and long-loop reasoning.
3. MLagent owns project memory, context assembly, evidence capture, experience distillation, knowledge indexing, and SkillVersion governance.
4. Persistent assets must stay human-readable and portable: Markdown, YAML, copied source files, and original evidence paths.
5. `indexes/` is rebuildable and never the only source of truth.
6. MVP is local and single-machine.
7. MVP has no mandatory vector database, graph database, workflow orchestrator, MLflow, DVC, Optuna, or model registry server.
8. Formal SkillVersion creation requires human review of training results and benchmark performance.
9. Experience may be automatically inserted, but must carry `confidence`, `needs_review`, and source references.
10. Context must load progressively: current prompt first, then data understanding, then experience, then project knowledge, then SkillVersion list.

## 3. Overall Verdict

The research is broadly aligned with the design, but it should be treated as a reuse decision map, not as an implementation blueprint to import wholesale.

High-confidence fit:

- Claude Code plugin structure and hook placement.
- Lightweight CLI plus schema validation.
- File-first memory repo with SQLite FTS5 index.
- Knowledge ingestion through narrow document extraction and chunking components.
- Three-layer memory model: raw memory, experience, SkillVersion.
- Progressive context loading and task-specific Context Packs.

Needs correction or downgrading:

- `iterative/mlem` is archived/read-only and should only be used as a historical schema reference, not a dependency or active upstream.
- Directly forking `obra/superpowers` should be interpreted as "copy/adapt the proven plugin skeleton and hook patterns"; implementation should start from official `claude plugin init` and copy only needed parts.
- Git PR review is a good approval pattern for Git-hosted projects, but the local MVP should use explicit CLI approval as the primary path.
- `sqlite-vec`, RRF, reranking, and hybrid retrieval should remain phase-two or optional; the MVP default remains SQLite FTS5 only.
- "Claude API direct implementation" for experience distillation should not become a required separate API integration. The MVP should use Claude Code skills and CLI files first; direct API calls are optional later.

## 4. Fit Score Rubric

Scores:

- 5: Directly reusable in MVP.
- 4: Reusable with thin wrapping or strict scoping.
- 3: Good design reference, but do not import runtime.
- 2: Useful concept only; high mismatch or operational risk.
- 1: Not suitable.

## 5. Module Evaluation

| Module | Research conclusion | Fit score | Decision |
|---|---:|---:|---|
| M1 memory systems | Borrow langmem, A-MEM, Graphiti models; do not import runtimes | 4 | Accept with guardrails |
| M2 knowledge ingestion | Use pypdf + langchain-text-splitters; optional markdownify | 5 | Accept |
| M3 SQLite FTS5 index | Use sqlite-utils + sqlite3 fallback | 5 | Accept |
| M4 Claude Code plugin | Use official plugin structure; reference superpowers hooks | 4 | Accept with "adapt, not wholesale fork" |
| M5 Context Packs | Borrow progressive loading; custom MLagent pack rules | 4 | Accept with FTS5-only MVP |
| M6 SkillVersion registry | Borrow MLEM/modelstore/schema/GitOps ideas | 3 | Accept as schema inspiration only |

## 6. M1 Memory Systems Assessment

The M1 research correctly rejects full memory runtimes. This is important because mainstream agent memory projects usually pull in one or more of: vector stores, graph databases, long-running servers, hosted LLM-specific flows, or opaque storage formats.

Accepted:

- Borrow LangMem's semantic/episodic/procedural classification as conceptual vocabulary.
- Borrow LangMem-style episodic fields for `experience`.
- Borrow A-MEM's atomic note shape: content, context, keywords, tags, related links.
- Borrow Graphiti's temporal idea: old facts and versions are superseded, not deleted.

Rejected:

- Do not import LangMem runtime into MVP.
- Do not use A-MEM's ChromaDB-backed implementation.
- Do not use Graphiti runtime, Neo4j, FalkorDB, or graph extraction pipeline.
- Do not make mem0, Letta, cognee, Redis memory server, or Kernel Memory runtime dependencies.

Required implementation interpretation:

```text
raw_memory: MLagent-owned YAML records
experience: MLagent-owned atomic YAML cards with source, confidence, review state, validity
skill_versions: MLagent-owned approved retraining procedures with temporal version fields
```

Feasibility: high. The research adapts well because it extracts durable schema ideas while avoiding runtime lock-in.

Risk: medium if implementation accidentally imports a memory framework to save time. This would violate portability and MVP scope.

## 7. M2 Knowledge Ingestion Assessment

The M2 recommendation is well adapted to the design.

Accepted runtime dependencies:

- `pypdf` for basic non-scanned PDF text extraction.
- `langchain-text-splitters` for text and Markdown chunking.
- Optional `markdownify` for HTML conversion.

Accepted behavior:

- Copy original files into `project_knowledge/originals/`.
- Store SHA-256, source path, stored path, import time, title, tags, and summary.
- Extract text, chunk it, summarize it, and write the chunks into SQLite FTS5.

Rejected:

- PyMuPDF as a default dependency because of AGPL distribution risk.
- Marker because it is too heavy for MVP and pulls ML/OCR dependencies.
- Docling standard mode because it can pull heavyweight ML dependencies.
- Unstructured, LangChain, or LlamaIndex as whole frameworks.

Required caveat:

MVP PDF support is "basic text extraction", not OCR or layout-faithful scientific PDF parsing. Scanned PDFs, complex tables, formulas, and multi-column extraction quality are explicitly outside the MVP unless manually corrected or handled by a later optional backend.

Feasibility: high. This is one of the safest direct-reuse modules.

## 8. M3 SQLite FTS5 Assessment

The M3 recommendation is strongly aligned with the design.

Accepted:

- Use SQLite FTS5 as the MVP search backend.
- Use `sqlite-utils` to reduce boilerplate for tables, upserts, FTS setup, and rebuild operations.
- Use Python standard-library `sqlite3` to detect FTS5 availability and as a fallback path.

Required design guardrails:

- `indexes/memory.sqlite` is rebuildable.
- Every indexed item must point back to a durable source file or YAML record.
- The index must never contain the only copy of any memory asset.
- Index schema must include asset type and source path to support Pack-specific retrieval.

Rejected:

- Meilisearch, Tantivy, or any search service that needs a daemon.
- sqlite-vec in MVP default path.
- Vector-only retrieval.

Feasibility: high. It is technically simple and fits the local-first memory repo.

## 9. M4 Claude Code Plugin Assessment

The M4 research is directionally correct and externally verified. Claude Code plugins support `.claude-plugin/plugin.json`, `skills/`, `agents/`, `hooks/`, `.mcp.json`, `monitors/`, `bin/`, and plugin-root `settings.json`. `bin/` executables are added to the Bash tool PATH while the plugin is enabled. Plugin hooks live under `hooks/hooks.json`.

Accepted:

- Start from official Claude Code plugin scaffolding.
- Use `skills/` for the five MLagent workflow skills.
- Use `bin/mlagent-memory` as the deterministic local CLI.
- Use command hooks in `hooks/hooks.json`.
- Use `SessionStart`, `PostToolUse`, `PostToolBatch`, and `Stop` conservatively.
- Use `PostToolBatch` preferentially for batch summaries when possible.
- Keep MCP deferred.

Adjusted interpretation of "fork obra/superpowers":

Do not carry over unrelated superpowers skills or behavior. Use it as a proven reference for plugin layout, session-start hook shape, JSON escaping, and additionalContext injection. The actual MLagent plugin should be generated from official scaffolding, then selectively copy/adapt needed hook and test patterns.

Risks:

- Hooks can easily over-record private or noisy data.
- `SessionStart` additional context can become too large and pollute the modeling session.
- Hook behavior may vary across Claude Code versions, so implementation must validate against local Claude Code.

Feasibility: high, with careful local validation.

## 10. M5 Context Pack Assessment

The M5 research fits the design, but the implementation must stay stricter than the research suggestions.

Accepted:

- Borrow Anthropic skills' progressive disclosure pattern.
- Use L0/L1/L2/L3 loading.
- Use filesystem-context rules: large outputs, long-lived evidence, multi-turn scratchpads, and handoff material should become files, not prompt bulk.
- Use confidence filtering: low-confidence experience is folded or marked "reference only".
- Implement four MLagent-specific Pack types:
  - Exploration Pack
  - Retraining Pack
  - Experience Distillation Pack
  - SkillVersion Candidate Pack

Required correction:

The research mentions optional hybrid retrieval with sqlite-vec and RRF. This is acceptable only as a phase-two extension. MVP Context Packs must be built from deterministic rules plus SQLite FTS5.

Accepted MVP retrieval order for exploration:

1. Current user prompt.
2. Relevant `data_understanding`.
3. Relevant high/medium confidence `experience`.
4. Relevant `project_knowledge`.
5. Available `skill_versions` list as reference only.

Feasibility: high, because it is mostly custom orchestration over local files and FTS5.

Risk: medium. Poor ranking or oversized Packs can degrade Claude Code's exploration. The MVP must define token budgets and truncate aggressively.

## 11. M6 SkillVersion Registry Assessment

The M6 research is conceptually useful but needs the most correction.

Accepted:

- Borrow MLEM's object metadata pattern: `object_type`, `artifacts`, `requirements`, `params`.
- Borrow modelstore's separation of model/storage/code/version/extra metadata.
- Borrow lifecycle state names: `draft`, `pending_review`, `approved`, `rejected`, `archived`.
- Borrow GitOps/PR review as an optional approval and audit mechanism.
- Keep `performance.yaml` mandatory for approved SkillVersions.

Corrections:

- `iterative/mlem` is archived/read-only and should not be used as an active dependency or upstream implementation.
- The research document should treat MLEM as historical schema inspiration only.
- Local MVP should not depend on GitHub/GitLab PR availability. Explicit CLI approval remains the required base path.
- PR review becomes an optional adapter for projects already hosted in Git.

Required approval rule:

```text
candidate_skill_version
  -> human review of performance and reproducibility
  -> approve-skill with reviewer, timestamp, benchmark metrics, dataset version, evidence links
  -> formal skill_versions/vXXX insertion
```

Feasibility: medium-high. The file-backed schema is straightforward; the hard part is enforcing approval boundaries and preventing Claude Code from treating candidates as approved assets.

## 12. Cross-Document Issues Found

### 12.1 MLEM status and license mismatch

The local M6 research describes MLEM as MIT and positions it strongly as a model registry reference. External verification shows the repository is archived/read-only and GitHub reports Apache-2.0. The design must not depend on it.

Resolution:

- Keep MLEM only as schema inspiration.
- Do not import or vendor it.
- Do not describe it as active infrastructure.

### 12.2 "fork superpowers" may be too strong

The research says "fork obra/superpowers". That is acceptable as shorthand for learning from a proven plugin skeleton, but too broad as an implementation instruction.

Resolution:

- Use official `claude plugin init` as the canonical starting point.
- Copy/adapt specific hook patterns from superpowers.
- Do not inherit unrelated skills, policies, or workflows.

### 12.3 Direct Claude API distillation may conflict with Claude Code-first design

Some research text says distillation should use Claude API directly. That would introduce a separate LLM integration surface and credentials.

Resolution:

- MVP distillation should be Claude Code skill-driven and file/CLI-mediated.
- Direct API distillation may be phase two if unattended batch distillation becomes necessary.

### 12.4 Optional vector retrieval appears too close to MVP

M5 discusses sqlite-vec and RRF. This is technically reasonable, but it can blur the MVP boundary.

Resolution:

- MVP: SQLite FTS5 only.
- Phase two: optional sqlite-vec plus RRF if FTS5 recall is insufficient.
- Never make vector retrieval the only route to memory assets.

### 12.5 Hook breadth needs stricter capture policy

The research identifies many Claude Code hook events. More hooks are not automatically better.

Resolution:

- MVP hook set: `SessionStart`, `PostToolUse`, `PostToolBatch`, `Stop`.
- Defer `PreCompact` and `PostCompact`.
- Do not capture full tool responses by default.
- Prefer summarized event records and evidence paths.

## 13. Approved Reuse Plan

### Direct runtime dependencies for MVP

```text
typer
pydantic
pyyaml or ruamel.yaml
pypdf
langchain-text-splitters
sqlite-utils
markdownify optional
```

### Standard-library dependencies

```text
sqlite3
hashlib
pathlib
json
datetime
subprocess
shutil
```

### Reference-only projects

```text
langmem       -> experience schema and distillation pattern
A-MEM         -> atomic memory card and related links
Graphiti      -> temporal validity and provenance
MLEM          -> archived schema inspiration only
modelstore    -> lifecycle state and metadata separation
superpowers   -> plugin/hook skeleton patterns
anthropics/skills -> progressive disclosure
Agent-Skills-for-Context-Engineering -> filesystem-context rules
```

### Explicitly excluded from MVP

```text
mem0 runtime
letta runtime
cognee runtime
graphiti runtime
LangChain full framework
LlamaIndex full framework
Unstructured full framework
MLflow
DVC
Optuna
Qdrant / Chroma / Pinecone
Neo4j / FalkorDB
Marker
PyMuPDF default dependency
Docling standard mode
workflow orchestrators
```

## 14. Implementation Implications

The implementation plan should follow this order:

1. Scaffold the plugin with official Claude Code plugin layout.
2. Add `bin/mlagent-memory` with Typer command skeleton and Pydantic models.
3. Implement `project_memory/` initialization and schema validation.
4. Implement SQLite FTS5 index and search with rebuild guarantee.
5. Implement knowledge import for TXT, Markdown, and basic PDF.
6. Implement raw memory and experience YAML write paths.
7. Implement Exploration and Retraining Context Pack generation using FTS5 only.
8. Implement candidate SkillVersion creation and local explicit `approve-skill`.
9. Add optional Git PR approval adapter only after local approval works.
10. Add hooks after CLI write paths are stable, not before.

This order avoids building hooks or Claude Code skills on top of untested storage primitives.

## 15. Acceptance Criteria for Research Fit

The research is considered implementation-ready only if these checks remain true:

- No direct dependency on a memory runtime.
- No required vector database or graph database.
- No required training framework or experiment tracker.
- Every durable artifact can be inspected without running MLagent.
- Every index can be deleted and rebuilt.
- Every automatically generated experience item links to raw evidence.
- Every approved SkillVersion has human review metadata and performance details.
- Candidate SkillVersions cannot be used by `retrain-from-memory` unless explicitly requested as drafts.
- Claude Code hooks never store full logs, full diffs, training data, or model binaries by default.

## 16. Final Recommendation

Proceed with the research-backed architecture, with the corrections above.

The research is sufficiently adapted to MLagent's design if implementation treats the ecosystem as follows:

```text
Reusable libraries: narrow, local, Python-only utilities.
Reusable projects: schema and workflow inspiration, not runtime foundations.
Reusable plugin code: skeleton and hook patterns, not unrelated behavior.
Reusable approval model: explicit human gate, local-first, Git PR optional.
```

This preserves the core MLagent identity: a portable project memory asset system that lets Claude Code explore and retrain with better context, without becoming a training framework, RAG platform, or model registry server.

## 17. External Verification Notes

External checks performed on 2026-06-22:

- Claude Code plugin docs confirm plugin directories include `.claude-plugin/plugin.json`, `skills/`, `hooks/`, `.mcp.json`, `monitors/`, and `bin/`; `bin/` executables enter the Bash PATH when the plugin is enabled.
- Claude Code hooks docs confirm plugin hooks use `hooks/hooks.json`, and `PostToolBatch` runs once after a batch of tool calls resolves.
- `pypdf` describes itself as a pure-Python PDF library and supports text and metadata retrieval from PDFs.
- `sqlite-utils` describes itself as a Python CLI and library for SQLite, with full-text-search support.
- PyPI reports `langchain-text-splitters` as MIT licensed and Python >=3.10.
- GitHub reports `iterative/mlem` as archived/read-only since 2023-09-13, Apache-2.0 licensed.
