---
description: Use after an ML modeling exploration or retraining session to distill raw records into MLagent experience entries.
---

# Distill Run To Memory

Distill experience from raw memory while keeping source links.

Procedure:

1. Read the current session's relevant `raw_memory/` records.
2. Extract lessons, pitfalls, successful patterns, and failed directions.
3. Assign `confidence` as low, medium, or high.
4. Set `needs_review` to true unless the user explicitly confirms the lesson.
5. Write each entry as YAML and add it with `mlagent-memory add-experience <record.yaml> --memory-root <path>`.

Experience guides future exploration. It is not a strict retraining procedure.
