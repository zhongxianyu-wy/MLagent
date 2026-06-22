---
description: Use when the user asks to retrain using a specific approved MLagent SkillVersion.
---

# Retrain From Memory

Strict retraining uses an approved SkillVersion as the controlling procedure.

Procedure:

1. Require the user to specify a SkillVersion.
2. Run `mlagent-memory create-context-pack "<prompt>" --pack-type retraining --skill-version <version> --memory-root <path>`.
3. Follow `reproduce.md`, `constraints.md`, and `validation_checklist.md`.
4. Do not apply exploration advice unless the user explicitly asks to optimize while retraining.
5. Record the retraining run through `mlagent-memory add-raw <record.yaml> --memory-root <path>`.

Candidate SkillVersions are not approved retraining assets unless the user explicitly asks to inspect a draft.
