---
description: Use when starting ML modeling work in a project that should use MLagent project memory. Requires choosing a Project Memory Repo before exploration or retraining.
---

# Start Modeling Session

Load only the project manifest and a small startup context.

Procedure:

1. Ask the user to confirm the target `project_memory/` path if it is not explicit.
2. Run `mlagent-memory status --memory-root <path>`.
3. Ask for the current modeling goal or use the user's current prompt.
4. Run `mlagent-memory create-context-pack "<goal>" --pack-type exploration --memory-root <path>`.
5. Treat the returned pack as guidance, not as a replacement for the user's current goal.

Do not load full `raw_memory/` or full project documents during startup.
