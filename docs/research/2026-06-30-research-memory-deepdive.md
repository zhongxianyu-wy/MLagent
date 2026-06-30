# MLagent v0.3 Memory Subsystem — Deep GitHub Research (Design-Inspiration Only)

> Backref: [redesign spec](../superpowers/specs/2026-06-26-mlagent-redesign-spec.md) · Date: 2026-06-30 · Branch: `v0.3`
> Deepens prior research (mem0/langmem/A-MEM/Letta/Graphiti/cognee/MLEM/modelstore/DVC/GTO/W&B/MLflow/OpenLineage/SLSA/spec-kit/skill-creator). This sweep went **broader** (2025-2026 coding-agent-specific + ML-experiment-as-memory + versioned-procedural-memory) and **deeper** (extracted actual data models + workflow, not just "has memory"). Forbidden runtime unchanged: file-first YAML/MD + optional SQLite; **no** vector-DB / graph-DB / mem0 / Letta / MLflow / Neo4j / Redis.

## 1. Comparison table (NEW, most-relevant repos)

| repo | ★ | layer model | distill trigger & decision logic | confidence/review gate | versioning / supersession | traceability | scoping | relevance | borrowable pattern | forbidden runtime |
|---|---|---|---|---|---|---|---|---|---|---|
| **Dicklesworthstone/cass_memory_system** | ~391 | **3-layer (Episodic raw → Working diary → Procedural playbook)** — near-1:1 to ours | **ACE Pipeline**: Generator→Reflector→Validator→**Curator (NO LLM, deterministic)**. Deltas: `add / helpful / harmful / deprecate`. Triggered by "unprocessed sessions" batch (like our staged-by-count) | **maturity machine**: `candidate→established→proven→deprecated`; "Scientific validation" gate searches history for evidence before ACCEPT | `state: draft\|active\|retired` + deprecated flag; anti-pattern inversion (harmful→warning) instead of delete | `sourceSessions[]`, `sourceAgents[]`, `reasoning`, `feedbackEvents[]` immutable log | scope: `global\|workspace\|language\|framework\|task` | **HIGH** | maturity FSM + deterministic Curator + feedback-decay score + anti-pattern inversion | Bun/TS runtime (borrow schema+logic only) |
| **esaradev/icarus-memory-infra** | ~292 | **3-layer (working-memory scratch / session-archive per-agent / shared wiki)** + markdown on disk, MCP-native | `start_session`→briefing; `end_session`→archive + `promote_to_wiki[]` (explicit promotion list) | **`verified` lifecycle**: `unverified→verified→contradicted→rolled_back`; `verify()` only via downstream re-grounding, NOT write-time | **non-destructive rollback** via `revises` chain to nearest verified ancestor; `contradicted_by`, `review_of` typed links | **EvidencePointer** `{kind: file\|url\|fabric_ref\|tool_output\|message, ref, excerpt, sha256}`; tamper-detect via hash | agent_id (but their audit flags cross-agent wiki-leak bug) | **HIGH** | EvidencePointer schema + `verified` lifecycle + typed links + write-time validation rules + their **v0.3 audit gaps as our gotchas** | their OpenAI classify step (we use Claude) |
| **boshu2/agentops** | ~400 | "validation membrane" + `.agents/` corpus (learnings→patterns→compiled); **Claude-Code-native plugin** | `/evolve` = outer loop (N× rpi); `/post-mortem` = "council validates, extracts learnings, **activates/retires knowledge**" (INSERT/SUPERSEDE concrete) | **ratchet pawl-gate**: (1) no self-grade (`context_id != author`, ≥2 model families), (2) fresh-agent-on-failure, (3) fail-closed, (4) commit+evidence-bound | promotion = learnings→patterns→compiled; `/release` does version bumps+tagging | proof trail = verdicts/catches/**escapes** (CONFIRMED-then-wrong) in `.agents/`, grep-able MD | per-repo `.agents/` | **HIGH** | **pawl-gate rules for our SOP reproduction test** + "escape-corpus" = our `failed_directions` + `/council` independent-judge pattern | Go CLI runtime (borrow gate rules) |
| **zhangfengcdt/memoir** | ~587 | hierarchical semantic-path memory + **Git-like versioning** (branch/commit/merge/rollback); Claude-Code/Codex plugin | auto-capture on session hooks; `remember` with confidence-threshold classifier | **confidence_thresholds**: `high(>0.8)→auto-store / medium(>0.5)→review / low→reject` | ProllyTree content-addressed store (SHA-256); `memoir blame/checkout` to audit/revert hallucination | content-addressed (SHA-256 per memory); `memoir blame` = who-taught-this-rule | per-store, branch-aware (respects `git checkout`) | **HIGH** | confidence-threshold gate (high/med/low) + `blame`/`checkout` for memory + branch-aware scoping | ProllyTree store + LLM classifier (borrow logic, use YAML) |
| **Ori-Mnemos (aayoawoyemi)** | ~312 | knowledge-graph vitality (identity/knowledge/ops zones) + **Recursive Memory Harness** | RMH: retrieval-as-navigation; recursive sub-question decomposition w/ convergence detection | **ACT-R base-level decay** with **per-zone multipliers** (identity 0.1× / knowledge 1.0× / ops 3.0×); Tarjan protects critical nodes at prune | "validate notes on write"; lifecycle zones | Hebbian co-retrieval edges (NPMI-normalized) | 3 zones (identity/knowledge/ops) | **MED-HIGH** | **per-zone decay multipliers** (refine cass's flat half-life: SOPs barely fade, low-conf pitfalls fade fast) + structural-criticality protection | Neo4j/graph + embeddings (borrow decay math only) |
| **gavdalf/total-recall** | ~267 | 5-layer observational | Observer→`observations.md`→Reflector→**Dream Cycle (nightly consolidation)** | dream-cycle consolidates | — | observations.md (file-first) | per-agent | **MED** | Observer→Dream-Cycle nightly = our "staged distill trigger" (background, not per-turn) proven pattern | shell scripts (borrow trigger concept) |
| **VectorSpaceLab/general-agentic-memory (GAM)** | ~857 | hierarchical taxonomy (LLM chunk→Memory+TLDR→taxonomy dirs) | `gam-add` LLM chunking + incremental add; dual-agent Memorizer+Researcher | — | incremental append (no supersession) | hierarchical dirs (taxonomy paths) | per `gam_dir` | **MED** | "long-horizon agent-trajectory compression" = our raw→experience compression of training sessions | FastAPI/Docker/embeddings (borrow chunking concept) |
| **agentops `/council`** | (within agentops) | multi-model judge primitive | auto-extract significant findings from WARN/FAIL into flywheel | **fresh-context, different-model** judges return one verdict | findings→learnings promotion | proof artifacts | — | **HIGH** | **independent-judge verification** for SOP gate (addresses icarus "compromised verifier" caveat) | — |

> Papers (no repo, flagged): **EDV (Execute-Distill-Verify, 2026)** — third-party distillation agent compares candidate trajectories + consensus verification before memory insertion. Conceptually = our raw→experience→SOP-verify decoupling. No public code (uncertainty). **"Don't Ask the LLM to Track Freshness" (2026)** — validates cass's deterministic-Curator choice.

## 2. NEW projects not in prior research (genuinely new)

- **cass_memory_system** — the single highest-value NEW find. First repo implementing the *exact* three-layer cognitive model (episodic→working→procedural) AND a working distill pipeline (ACE) with a **deterministic Curator (no LLM)** plus a **maturity FSM** (`candidate→established→proven→deprecated`) and **feedback-decay scoring** (90-day half-life, 4× harmful multiplier). Prior research had langmem (schema only) — cass gives the *machinery*.
- **icarus-memory-infra** — NEW. The only repo with our exact architecture (3-layer + markdown + supersession + provenance) AND it publishes its **`verified` lifecycle** (`unverified/verified/contradicted/rolled_back`) and **non-destructive rollback**. Bonus: its `docs/v03-audit-gaps.md` is a ready-made list of *our* future bugs (cross-agent wiki leak, stale rendered body on mutation, unbounded page growth).
- **agentops (boshu2)** — NEW. The **ratchet pawl-gate** ("no self-grade / fresh-agent-on-failure / fail-closed / commit+evidence-bound") is the most rigorous formulation of a promotion gate — directly solves our "instance→SOP must pass reproduction test + human approval." Also "escape-corpus" = a principled origin for our `failed_directions`.
- **memoir** — NEW. "Git for AI Memory" with `blame`/`checkout`/branch-aware memory and a **confidence-threshold classifier** (`high→auto / med→review / low→reject`) — the cleanest confidence-gate formulation.
- **Ori-Mnemos RMH** — NEW. **Per-zone decay multipliers** (identity 0.1× / knowledge 1.0× / ops 3.0×) + ACT-R base-level decay + Tarjan critical-node protection — refines cass's flat half-life into "different layers fade at different rates."
- **EDV paper / Deterministic-conflict paper** — NEW conceptual backing (no code) for decoupled distill+verify and deterministic conflict resolution.

(Tangential, excluded: `redis/agent-memory-server` — Redis-bound; `neo4j-labs/agent-memory` — Neo4j-bound; `swarmvault`/`repomemory`/`consolidation-memory` — too early/FAISS-bound/sketchy; `TencentDB-Agent-Memory` — vendor DB; covered already in prior research and re-confirmed out-of-scope.)

## 3. Concrete v0.3 recommendations (each cites inspiration)

### (a) Auto-distill mechanism — trigger + INSERT/UPDATE/LINK/SUPERSEDE/NOOP

**Trigger rule** (cite **cass ACE Reflector** + **total-recall Dream-Cycle** + **Letta dream**):
- **Background/batched** (not per-turn): fire `distill` when `count(raw_memory since last_distill_at) ≥ N` (N=5 explorations) OR on `Stop` hook OR manual `/distill`. This is cass's "process unprocessed sessions" + Letta's "step-count/compaction" trigger — *already in spec §4.2, confirm N configurable*.
- **Hot-path exception** (cite **langmem active formation**): hook writes a `confidence:low, needs_review:true` raw *immediately* on run-failure/metric-jump/dead-end — do not wait for the batch. (icarus working-memory scratch + promote-on-end is the analogue.)

**Decision logic — two-stage, mirroring cass ACE (Reflector=LLM, Curator=deterministic)**:
- **Stage 1 — Reflector (LLM, Claude API, Episode prompt from langmem)**: review `raw_memory[created_at > last_distill_at]`; emit proposed deltas as `{op, rule, evidence_raw_ids, reasoning}`. Ops = `INSERT / UPDATE / LINK / SUPERSEDE / NOOP`. **NOOP is the default** when no meaningful change (performance gain or generalizable pitfall) — *cite cass "Skip noise" + spec §4.2*.
- **Stage 2 — Curator (DETERMINISTIC, no LLM — cite cass ACE Stage 4 + "Don't-Ask-LLM-to-Track-Freshness" paper)**: apply deltas with hash-based duplicate detection, conflict detection, and merge. **Keep this stage LLM-free** to prevent feedback-loop drift (cass's explicit rationale) and reproducibility.

**Concrete decision logic to adapt**:
- INSERT — `cass reflector` prompt (imperative rule, categorize, scope, reasoning) + **EDV**: verify candidate against history (≥K supporting raw runs, success ratio) before ACCEPT, else stay `candidate`. → *new experience gets `maturity: candidate`.*
- UPDATE — refine existing (patch in place, append `source_raw_records`, bump `valid_from`). *cite langmem `enable_updates`.*
- LINK — `cass add` with conflict-check + bidirectional `related`. *cite A-MEM write-time backlinks.*
- SUPERSEDE — contradiction + higher confidence/multi-source → new file `supersedes:[old]`, old gets `superseded_by` + `valid_to=now`, **never delete**. *cite icarus `contradict()` + Graphiti bi-temporal.*
- NOOP — already-equivalent captured (mem0 "cheese-pizza" rule).

### (b) Experience schema fields (additions to current `ExperienceRecord`)

Current schema has `confidence/needs_review/source_raw_records/applies_when/valid_from/superseded_by`. **Add** (cite cass `PlaybookBullet` + icarus):
```yaml
# NEW fields (all file-first YAML)
decision: insert            # insert|update|link|supersede|noop — how this record was produced
maturity: candidate         # candidate|established|proven|deprecated  (cass maturity FSM)
effective_score: 0.0        # decay-adjusted score, computed (cass getEffectiveScore)
feedback_events: []         # immutable append-only: {id,type:helpful|harmful,ts,source:run|human|audit,reason}
decay_half_life_days: 90    # per-record; override per layer (cass + Ori per-zone multipliers)
verified: unverified        # unverified|verified|contradicted|rolled_back (icarus verified lifecycle)
contradicted_by: null       # exp_id (icarus)
content_sha256: ...         # tamper-evidence (SLSA + icarus evidence hash)
derived_from: [raw://...]   # explicit typed edge, upgrade of source_raw_records (Graphiti episode edge)
```
**Refinement over cass**: adopt **Ori per-zone decay multipliers** — set `decay_half_life_days` long (e.g. 365) for `successful_pattern`/promoted-to-skill, short (e.g. 30) for `failed_direction`/low-confidence pitfalls. Keeps proven SOPs alive, lets stale guesses fade.

### (c) skill_library versioned-skill structure + supersession

Version metadata — spec §8.3 already has `background/reason/key_params/key_optimizations`. **Add a promotion `gate` block** (cite **agentops pawl-gate** + icarus `verified` + prior MLEM/modelstore):
```yaml
gate:                                # cite agentops ratchet pawl-gate (4 rules)
  tests_passed: true
  test_command: "python scripts/reproduce_v003.py"
  test_log: evidence/tests/run_20260626.log
  verifier_context_id: claude-opus-4-review   # != author agent (no self-grade)
  verifier_model_family: opus                   # >=2 model families for high-risk
  head_sha: abc123d                             # commit-bound
  acceptance_gate: {metric: auc, min_value: 0.90, tolerance: 0.005}
  human_review: {reviewed: true, reviewer: ..., approval_note: ...}
state: draft                  # draft|pending_review|approved|rejected|archived
verified: verified            # icarus — only set via gate, never write-time
status: current               # current|superseded (spec)
superseded_by: null           # set on old version when new promoted (Graphiti)
# supersession is NON-DESTRUCTIVE: old version -> status:superseded + verified:rolled_back, never deleted (icarus rollback contract)
```
**Critical borrow from agentops**: the SOP reproduction test must run under a **fresh context (`context_id != author`) and ideally a different model family** — directly defeats icarus's documented "compromised verifier" failure mode (a verifier that blesses everything). **Fail-closed**: no CONFIRMED verdict → stays `draft`/`pending_review`.

### (d) Traceability links

Adopt **icarus `EvidencePointer`** as the canonical link structure (cleaner than current flat `source_raw_records: [id]`):
```yaml
evidence:                       # icarus EvidencePointer
  - {kind: raw_ref,   ref: raw://raw_20260626_001, excerpt: "...", hash: <sha256>}
  - {kind: run_ref,   ref: runs/run_001/metrics.json, hash: <sha256>}
  - {kind: file,      ref: scripts/train_v003.py, hash: <sha256>}
  - {kind: exp_ref,   ref: exp://exp_20260626_001}      # skill promoted from experience (closes 3-layer chain)
  - {kind: tool_output, ref: tool_call_abc}
```
- Typed links (icarus + prior edge table): `revises`, `review_of`, `contradicted_by`, `derived_from`, `supersedes`.
- Reverse links already in the design (`derived_experiences`/`derived_skills` on raw) — keep.
- **Tamper-evidence**: every evidence pointer carries `hash`; on `trace`, recompute and compare — mismatch = upstream drift (icarus + prior SLSA/DVC `lineage.lock.yaml`).

## 4. Borrow vs forbidden table

| Borrow (pattern → file-first realization) | Forbidden runtime (the inspiration uses it; we don't) |
|---|---|
| cass maturity FSM `candidate→established→proven→deprecated` → YAML `maturity` field | cass Bun/TS runtime, its cass search engine |
| cass deterministic Curator (no LLM) → our `distill` Stage-2 Python | cass embedding vectors (768-dim) |
| cass feedback-decay score (90-day, 4× harmful) → `effective_score` computed in CLI | — |
| cass anti-pattern inversion (harmful rule → warning) → `failed_directions` auto-creation | — |
| **icarus `EvidencePointer` `{kind,ref,excerpt,hash}`** → YAML `evidence[]` | icarus OpenAI classify-on-write; its `[embeddings]` extra |
| **icarus `verified` lifecycle + non-destructive rollback** → `verified`/`status`/`superseded_by` | icarus fabric substrate (we use our own dirs) |
| **agentops pawl-gate** (no-self-grade / fresh-agent / fail-closed / commit+evidence-bound) → SOP `gate` block | agentops Go CLI, `.agents/` corpus daemon |
| agentops `/council` independent multi-model judges → SOP reproduction verifier | agentops `/swarm`, NTM/ATM orchestration |
| agentops "escape-corpus" → `failed_directions` experience type | — |
| memoir confidence-threshold classifier (`high/med/low`) → distill accept/reject gate | memoir ProllyTreeStore, its LLM path-classifier |
| memoir `blame`/`checkout` → git is already our registry (prior MLEM) | memoir ProllyTree content store |
| **Ori per-zone decay multipliers** → per-record `decay_half_life_days` by type | Ori Neo4j graph, embeddings, PageRank |
| total-recall Observer→Dream-Cycle → hook-writes-raw + Stop-triggers-distill | total-recall shell daemon |
| EDV decoupled execute→distill→verify → our 3-stage separation | (paper only, no code) |

## 5. Sources (URLs)

**Top NEW (deeply inspected — README + source/schema)**:
- cass_memory_system — https://github.com/Dicklesworthstone/cass_memory_system (README ACE Pipeline / Data Models / Scoring; `.cass/playbook.yaml` + `test/fixtures/playbook-sample.yaml`)
- icarus-memory-infra — https://github.com/esaradev/icarus-memory-infra (README; `docs/DESIGN.md`, `docs/PROVENANCE.md`, `docs/v03-audit-gaps.md`)
- agentops — https://github.com/boshu2/agentops (README; `docs/SKILLS.md`; `docs/3.0.md` for pawl-gate & fresh-agent-on-failure)
- memoir — https://github.com/zhangfengcdt/memoir (README; architecture https://zhangfengcdt.github.io/memoir/architecture/)
- Ori-Mnemos — https://github.com/aayoawoyemi/Ori-Mnemos (README RMH; paper https://orimnemos.com/rmh)
- total-recall — https://github.com/gavdalf/total-recall (README Observer/Dream-Cycle)
- general-agentic-memory — https://github.com/VectorSpaceLab/general-agentic-memory (README; paper https://arxiv.org/abs/2511.18423)

**Survey/curated (paper discovery)**:
- Awesome-AI-Memory — https://github.com/IAAR-Shanghai/Awesome-AI-Memory (EDV; "Don't Ask the LLM to Track Freshness")
- Awesome-Agent-Memory — https://github.com/TeleAI-UAGI/Awesome-Agent-Memory

**Uncertainties flagged**:
- EDV (Execute-Distill-Verify) and the deterministic-conflict-resolution paper are **paper-only** (no public repo) — borrow the *concept*, can't cite code.
- Star counts are point-in-time from `gh api` (2026-06-30); agentops/memoir/cass are fast-moving 2026 projects — re-check before depending on specifics.
- cass/icarus are **alpha/early-access** — borrow patterns, don't mirror their internal file layout blindly (icarus's own audit doc warns wiki ≠ substrate provenance asymmetry).

**Bottom line for the v0.3 gap**: the spec already nails the *what* (3 layers, staged distill, gate). This research fills the *how* with three concrete, battle-sketched mechanisms: **(1) cass's deterministic Curator + maturity FSM** for the distill decision logic, **(2) icarus's EvidencePointer + `verified` lifecycle** for traceability + non-destructive supersession, and **(3) agentops's pawl-gate** for the SOP reproduction gate (no-self-grade / fresh-verifier / fail-closed). All realizable in file-first YAML/MD + optional SQLite — zero new runtime deps.
