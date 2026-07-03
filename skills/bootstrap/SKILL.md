---
description: 会话开始时使用。了解 MLagent 工作流：如何记录 raw_memory（含 conclusion）、蒸馏经验、提升 SOP、重训。由 SessionStart hook 自动注入。
---

# MLagent Bootstrap

You are in a project with MLagent memory. This skill frames the workflow.

## The workflow (5 skills)

1. **explore-train** — user gives a goal/direction → you write code (flexible, grounded by injected experience/conventions) → run training → fill the `conclusion` block in raw_memory.
2. **distill-experience** — at session end (Stop hook) or on demand: review raw_memory since last distill → produce a distill plan (INSERT/UPDATE/LINK/SUPERSEDE/NOOP) → `mlagent distill --plan <file>`.
3. **instance-to-sop** — user says "this is the best" → run the reproduction test → `mlagent set-gate-result --tests-passed` → `mlagent approve-sop`.
4. **retrain-from-sop** — user picks an approved SOP version → `mlagent retrain <sop> <version>` → follow its procedure strictly → record results.

## How to record raw_memory

After each significant action (training run, exploration step, code change):
```bash
mlagent record-raw <record.yaml> --memory-root <path>
```
The record MUST include a `conclusion` block when the exploration reaches a verdict:
```yaml
conclusion:
  hypothesis: "what you expected"
  outcome: confirmed | refuted | inconclusive
  summary: "what happened"
  evidence: [runs/run_001/metrics.json]
```

## How experience feeds back

Before writing code for a new goal:
```bash
mlagent assemble-context "<goal>" --memory-root <path>
```
This injects: relevant experience (high/medium confidence, verified) + code conventions (from past SOPs) + approved SOP list. Use these to write code in the project's established style.

## Key rules

- Exploration is **flexible** — no enforced structure. But ALWAYS record the conclusion.
- Retraining from a SOP is **strict** — identical input → identical output. Follow the SOP's SKILL.md + scripts exactly.
- SOP promotion requires: gate test passed + human approval. Never auto-approve.
