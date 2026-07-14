# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

**MLagent_v3** is an NGS machine-learning experiment agent. The product vision is a local assistant that:

- Understands user-provided feature matrices and grouping labels
- Standardizes inputs into a project dataset manifest
- Explores feature engineering directions, especially feature subset selection
- Reproduces approved training paradigms from Skills
- Accumulates experiment experience, literature/project methods, and reusable Skills

The target user is a bioinformatics or computational biology researcher who wants an AI assistant to automate repeated ML exploration while preserving reusable experience.

## Project Status

Early stage — no production code exists yet. Product, research, plan, and task materials are in `specs/`.

## Architecture Notes

The architecture baseline is defined in `specs/plan.md` and `specs/research/06-架构基线决策.md`. Expected components include:

- **Data intake** — LLM-assisted file exploration plus Socratic clarification, producing a standard feature/label manifest
- **Agent core** — Anthropic-compatible LLM planning and control
- **Training loop** — k-fold training, threshold selection, test-set evaluation when available
- **Memory system** — SQLite episodic traces, semantic knowledge, and Skill candidates
- **Skill system** — `skill-creator` compliant Skills, optimized by darwin-skill before human review
- **Research integration** — project-local muyu-search-mcp for literature and project investigation

## MCP Servers

Project-level MCP servers are configured in the project, not globally. Use the local muyu-search-mcp workflow from `/Users/zhongxianyu/Desktop/muyu-search-mcp` for research features.

<!-- SPECKIT START -->
## Spec Kit

Canonical Spec Kit feature artifacts live in `specs/001-ngs-ml-agent/`:

- `spec.md` — prioritized user stories and functional requirements
- `plan.md` — implementation plan, architecture, and contracts
- `tasks.md` — dependency-ordered task list
- `data-model.md` — core entities and validation rules
- `contracts/` — frontend/service and storage contracts

Use these files as the source of truth before implementation. Root `specs/plan.md` and `specs/tasks.md` are synchronized copies for compatibility.
<!-- SPECKIT END -->

<!-- SPECKIT START -->
For additional context about technologies to be used, project structure,
shell commands, and other important information, read the current plan
<!-- SPECKIT END -->
