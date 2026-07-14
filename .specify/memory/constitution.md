# MLagent_v3 Constitution

## Core Principles

### I. Conversation-First Interface

The default product entry MUST be a Claude Code-like LLM shell with ask, plan, and agent modes. One-shot CLI commands are allowed for automation, but they must not become the primary user experience.

### II. Test-First Development

All production code changes MUST follow Superpowers TDD: write or extend the relevant test first, observe the expected failure, implement the smallest passing change, then rerun the narrow and relevant broader tests.

### III. Deterministic Evaluation Integrity

The LLM MAY propose plans, questions, and experiment directions, but deterministic local code MUST compute metrics, thresholds, model artifacts, and stop conditions. Test-set predictions or labels MUST NOT be used for threshold selection or candidate selection.

### IV. Mode Safety Boundaries

Ask mode MUST NOT call project tools or mutate experiment state. Plan mode MAY read historical memory summaries and write validation-plan state, but MUST NOT write data/model artifacts, launch training, or mutate Skills. Agent mode MAY call tools only through services and safety hooks.

### V. Memory-Skill Separation

Episodic traces, semantic memory, Skill candidates, and approved Skills MUST remain linked but distinct. Dream jobs MAY summarize and deduplicate memory, but MUST NOT modify approved Skills. Skill publication or replacement MUST require human approval.

## Additional Constraints

- The system is local-first and single-user for MVP, but storage and APIs MUST support multiple sessions, datasets, runs, plans, dream jobs, and Skill optimization jobs.
- Functional slash commands and aliases MUST resolve through an auditable harness registry.
- Frontend clients MUST consume service/API contracts and MUST NOT talk directly to AIDE, MLflow, ChromaDB, or local files.
- Background jobs MUST use leases or equivalent locking before performing maintenance work.

## Development Workflow

- Spec, plan, contracts, and tasks MUST stay synchronized before implementation resumes.
- Each task in `tasks.md` MUST include a concrete file path and be executable under TDD.
- High-risk contracts require contract or integration tests before implementation: storage schema, mode guard, threshold leakage, Skill publishing, dream maintenance, Skill optimization, and frontend API streaming.

## Governance

This constitution supersedes ad hoc implementation choices. Amendments require updating affected spec, plan, contracts, tasks, and tests before proceeding.

**Version**: 1.0.0 | **Ratified**: 2026-05-26 | **Last Amended**: 2026-05-26
