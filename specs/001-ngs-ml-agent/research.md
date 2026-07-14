# Research: NGS ML Experiment Agent

## Decision: Use GitHub Spec Kit feature layout

**Rationale**: The official Spec Kit workflow organizes work as `spec.md` → `plan.md` → `tasks.md`, with optional `research.md`, `data-model.md`, `contracts/`, and `quickstart.md`. This keeps the prior PRD and architecture decisions executable by user story.

**Alternatives considered**: Continue using root `specs/plan.md` and `specs/tasks.md`. Rejected because it mixes product-level notes with implementation tasks and does not provide story-level independence.

## Decision: Put data intake before training

**Rationale**: User inputs can be multiple files with unknown matrix orientation, labels, and splits. A `DatasetManifest` prevents every downstream module from re-guessing file structure.

**Alternatives considered**: Require standard CSV input. Rejected because it contradicts the clarified requirement and pushes repeated manual prep back to users.

## Decision: Use Socratic clarification for ambiguous data intake

**Rationale**: The LLM can inspect files and infer candidates, but label semantics and split intent often require human confirmation. One blocking question at a time keeps the workflow lightweight and auditable.

**Alternatives considered**: Fully automatic inference. Rejected because label polarity, sample matching, and test-set use are high-impact decisions.

## Decision: Separate preprocessing from feature subset selection

**Rationale**: Standardization, binarization, missing-value handling, and encoding fixes must occur before subset selection. Low-variance and correlation filtering are treated as subset-selection strategies.

**Alternatives considered**: Treat all feature engineering as one undifferentiated search space. Rejected because it produces poor traces and makes Skill distillation ambiguous.

## Decision: Deterministic evaluation owns metrics and thresholds

**Rationale**: k-fold validation, threshold selection, and test-set scoring must be reproducible and independent from LLM reasoning. Thresholds are derived from concatenated validation-fold predictions only.

**Alternatives considered**: Let the LLM summarize or choose metrics from stdout. Rejected because it risks hallucinated metrics and test leakage.

## Decision: Use Anthropic-compatible provider configuration

**Rationale**: The project must support domestic and international Anthropic-compatible APIs such as GLM coding-plan-compatible endpoints. A provider config with `base_url`, `api_key_env`, `model`, and timeout is more robust than model-name regex.

**Alternatives considered**: Extend AIDE regex for `claude-*` only. Rejected as a short-term patch that does not satisfy provider portability.

## Decision: Use local muyu-search-mcp for research ingestion

**Rationale**: The local tool supports planned search, fetch, and site mapping. Complex literature/project research should follow its planning state machine before ingestion.

**Alternatives considered**: Generic web search. Rejected because the user explicitly requested the local muyu-search-mcp method and because structured source tracking matters for knowledge ingestion.

## Decision: Skill publishing requires SkillCandidate, skill-creator validation, darwin-skill iteration, and human approval

**Rationale**: Skills are executable procedural knowledge. They must follow `skill-creator` rules, be iterated using a darwin-skill-style loop, and remain unpublished until a human approves.

**Alternatives considered**: Directly write `.claude/skills/*/SKILL.md` from notebook or best run. Rejected because it risks publishing brittle, unvalidated, or misleading workflows.
