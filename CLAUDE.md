# MLagent (v0.3)

A Claude Code plugin for project-level ML modeling memory (raw → experience → Skill-SOP library), an interactive UI, and the skills/hooks that wire them together. Authoritative design: `docs/superpowers/specs/2026-06-26-mlagent-redesign-spec.md`.

## Agent skills

### Issue tracker

Issues live in GitHub Issues (github.com/zhongxianyu-wy/MLagent) via the `gh` CLI; external PRs are NOT a triage surface. See `docs/agents/issue-tracker.md`.

### Triage labels

Five canonical labels used as-is: `needs-triage` / `needs-info` / `ready-for-agent` / `ready-for-human` / `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `CONTEXT.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.
