# MLagent v0.4

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**MLagent** is a Claude Code plugin for reproducible NGS machine-learning exploration. It:

- Understands user-provided feature matrices and grouping labels
- Requires an approved exploration plan before training
- Captures minimal, traceable training facts and reviewable expert experience
- Turns only specified, reproduced training instances into versioned SOPs
- Keeps approved SOP models and their optimization background traceable
- Exposes code, data, runs, SOPs, experience, and lineage in a local Web UI

The target user is a bioinformatics or computational biology researcher who wants an AI assistant to automate repeated ML exploration while preserving reusable experience.

## Project Status

v0.4 establishes the approved product and architecture baseline. Prototype code exists, but requirements
newly introduced by the v0.4 PRD must not be described as implemented until their acceptance tests pass.

## Architecture Notes

The canonical product baseline is `specs/002-mlagent-plugin-memory-sop/prd.md`. The corresponding design
decisions are in `docs/superpowers/specs/2026-07-14-mlagent-plugin-memory-sop-design.md`, `CONTEXT.md`,
and `docs/adr/`. Older `specs/001-ngs-ml-agent/`, root plans, and research files are historical input.

- **Claude Code plugin** — Skills and Hooks orchestrate workflows and human decision gates.
- **Domain core** — deterministic services own data, runs, memory, SOP, models, and Git writes.
- **Team memory repository** — structured Git assets are the sole source of truth.
- **Local index** — derived, disposable, and rebuildable from authoritative assets.
- **Training execution** — frozen data/code/config/environment/seed inputs produce traceable instances.
- **Local Web UI** — six modules read and write only through domain services.

## MCP Servers

Project-level MCP servers are configured in the project, not globally. Use the local muyu-search-mcp workflow from `/Users/zhongxianyu/Desktop/muyu-search-mcp` for research features.

## Agent skills

### Issue tracker

Specs and implementation tickets live in GitHub Issues for `zhongxianyu-wy/MLagent`. See
`docs/agents/issue-tracker.md`.

### Triage labels

Use `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, and `wontfix`. See
`docs/agents/triage-labels.md`.

### Domain docs

This is a single-context repository: read `CONTEXT.md` and relevant ADRs under `docs/adr/` before
planning or implementation. See `docs/agents/domain.md`.

<!-- SPECKIT START -->
## Spec Kit

The approved v0.4 requirements live in `specs/002-mlagent-plugin-memory-sop/prd.md`. Do not implement
from `specs/001-ngs-ml-agent/`, root `specs/plan.md`, or root `specs/tasks.md` without first reconciling
them with the v0.4 PRD. Matt Pocock specs and tracer-bullet tickets published to GitHub Issues become
the implementation work queue after user approval.
<!-- SPECKIT END -->
