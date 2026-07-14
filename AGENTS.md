# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

**MLagent** is a Claude Code plugin for reproducible NGS machine-learning exploration. It:

- Understands user-provided feature matrices and grouping labels
- Requires an approved plan before training
- Captures traceable training facts and reviewable expert experience
- Produces versioned SOPs only from specified, independently reproduced training instances
- Preserves approved SOP models and their optimization background
- Provides a six-module local UI for code, data, runs, SOPs, experience, and lineage

The target user is a bioinformatics or computational biology researcher who wants an AI assistant to automate repeated ML exploration while preserving reusable experience.

## Project Status

v0.4 is the approved product and architecture baseline. Prototype code exists; new PRD requirements are
not implemented until their acceptance tests pass.

## Architecture Notes

Read `CONTEXT.md`, relevant ADRs under `docs/adr/`, the v0.4 PRD, and the v0.4 design decisions before
implementation. Older specs and root plans are historical input.

- **Claude Code plugin** — workflow orchestration through Skills and Hooks.
- **Domain core** — deterministic data, training, memory, SOP, model, and Git services.
- **Team memory repository** — structured Git assets are the sole source of truth.
- **Local index** — derived and rebuildable, never authoritative.
- **Local Web UI** — reads and writes through domain services only.

## MCP Servers

Project-level MCP servers are configured in the project, not globally. Use the local muyu-search-mcp workflow from `/Users/zhongxianyu/Desktop/muyu-search-mcp` for research features.

<!-- SPECKIT START -->
## Spec Kit

Canonical v0.4 product requirements live in `specs/002-mlagent-plugin-memory-sop/prd.md`. The matching
design baseline is `docs/superpowers/specs/2026-07-14-mlagent-plugin-memory-sop-design.md`. Do not use
`specs/001-ngs-ml-agent/` or root plan/task copies as implementation authority without reconciliation.
<!-- SPECKIT END -->

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
<!-- SPECKIT END -->
