---
description: Use at session end (Stop hook triggers automatically) or on demand to distill raw_memory into experience entries. Reviews raw since last distill, produces a structured plan, applies deterministically.
---

# Distill Experience

Reviews raw_memory since the last distill and produces **meaningful** experience entries (INSERT/UPDATE/LINK/SUPERSEDE/NOOP). No noise — if nothing meaningful happened, produce only NOOP.

## Procedure

1. Read raw_memory records created since the last distill (or all if first distill).
2. For each meaningful finding, decide:
   - **INSERT**: a new lesson/pitfall/pattern/convention not yet captured.
   - **UPDATE**: refines an existing experience (add evidence, bump confidence).
   - **LINK**: related to an existing experience (add backlink).
   - **SUPERSEDE**: contradicts an existing experience at higher confidence.
   - **NOOP**: already captured or no meaningful insight.
3. Write a distill plan YAML:
   ```yaml
   ops:
     - decision: insert
       experience:
         id: exp_001
         type: pitfall
         summary: "..."
         confidence: high
         needs_review: false
         source_raw_records: [raw_memory/runs/raw_001.yaml]
         created_at: "<ISO>"
     - decision: noop
   ```
4. `mlagent distill --plan <plan.yaml> --memory-root <path>`.

## Rules

- Only distill **meaningful** findings: performance gains, generalizable pitfalls, code conventions. Skip noise.
- Every experience MUST have `source_raw_records` (traceability).
- Conventions (code-style rules like "use 10-fold CV") go as type: `convention`.
- Confidence: `high` if corroborated by multiple runs; `medium` if single run; `low` if speculative.
