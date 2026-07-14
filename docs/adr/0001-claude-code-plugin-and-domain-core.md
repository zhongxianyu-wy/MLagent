# ADR-0001: Claude Code Plugin With An Independent Domain Core

- Status: Accepted
- Date: 2026-07-14

## Context

MLagent needs conversational planning and code modification while keeping training, metrics, validation,
and asset writes deterministic and testable.

## Decision

Claude Code remains the product entry point. Skills and Hooks orchestrate workflows and human gates.
An independent Python domain core owns data intake, training execution, memory, SOP/model lifecycle, Git
synchronization, and UI service contracts.

## Consequences

- Claude Code may propose plans and code but cannot invent training results or authoritative records.
- CLI, Hooks, and UI share the same domain services rather than duplicating business rules.
- The domain core is the primary high-level testing seam.
- Replacing the conversational shell does not require rewriting the domain model.
