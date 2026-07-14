# Domain Documentation

## Before Work

1. Read root `CONTEXT.md` and use its terms in specs, tickets, code, tests, and UI copy.
2. Read ADRs under `docs/adr/` that affect the area being changed.
3. Read the v0.4 PRD and the parent GitHub spec issue for behavioral scope.
4. Surface an ADR conflict explicitly; do not silently override an accepted decision.

## Layout

MLagent is a single-context repository:

```text
/
├── CONTEXT.md
├── docs/adr/
├── specs/002-mlagent-plugin-memory-sop/prd.md
└── src/
```

`CONTEXT.md` holds stable domain vocabulary and invariants. ADRs explain consequential technical or
product decisions. The PRD defines scope and acceptance; it must not be replaced by the glossary.

## Updating The Model

- Add or sharpen a term only when a real workflow needs it.
- Prefer one canonical term; record misleading synonyms under “Vocabulary To Avoid”.
- Create a new ADR when changing an accepted architectural constraint.
- Never edit an accepted ADR to hide history; supersede it with a new ADR.
