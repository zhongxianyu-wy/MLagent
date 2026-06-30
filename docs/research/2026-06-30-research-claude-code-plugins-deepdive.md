# Claude Code Plugin/Skill/Hook Ecosystem Research — for MLagent v0.3 Adapter

> Backref: [redesign spec](../superpowers/specs/2026-06-26-mlagent-redesign-spec.md) · Date: 2026-06-30 · Branch: `v0.3`
> Grounded in the v0.3 redesign spec and prior research (`2026-06-26-hooks-skills.md`, `2026-06-22-m4-claude-code-plugin.md`). This sweep **deepens** prior findings (obra/superpowers + official docs) with: sidecar-launching hooks, a UI-in-plugin precedent, a research-lab analog, marketplace path-resolution gotchas, and the dynamic-skill-discovery bridge. For DESIGN INSPIRATION + ecosystem norms; we stay Claude-Code-native.

## 1. Comparison table

| Plugin / repo | Purpose | Skills structure | Hooks used | Sidecar process from hook? | SessionStart injection | PostToolUse pattern | Marketplace / distribution | Relevance | Borrowable pattern |
|---|---|---|---|---|---|---|---|---|---|
| **ReflexioAI/claude-smart** | Self-improving plugin: turns corrections into preferences + project skills + shared skills; ships a **dashboard UI** | `plugin/.claude-plugin/` + `plugin/dashboard/` (Next.js) + `plugin/scripts/` | **6 hooks**: Setup, SessionStart (×4 cmds), UserPromptSubmit, PreToolUse, PostToolUse (`*`), Stop, SessionEnd | **YES — definitive example.** `backend-service.sh start` (FastAPI :8071) + `dashboard-service.sh start` (Next.js :3001) launched from SessionStart, **detached** | `hook_entry.sh` → JSONL buffer + reflexio search → `additionalContext` (query-keyed, per turn via UserPromptSubmit/PreToolUse, not just SessionStart) | `PostToolUse` matcher `*` → records tool invocations to JSONL for later extraction; **records, doesn't block** | `marketplace.json` `source:"./plugin"` (local-subdir) | **HIGH** | UI-sidecar lifecycle (§3b); per-turn context injection; skill status lifecycle CURRENT→ARCHIVED; `claude -p` subprocess as LLM backend for distill |
| **LigphiDonk/Oh-my-paper** | Research-lab plugin: literature survey → experiment → paper writing, with agent team + memory | `plugins/oh-my-paper/{skills,agents,commands,hooks}`; 34 skills incl. **bioinformatics-init-analysis, dataset-discovery, inno-experiment-analysis** (ML skills with `scripts/`) | SessionStart (node, timeout 10), Stop (timeout 15), PostToolUse `Write` (stage-transition) | Sidecar is an **MCP server over stdio** for remote experiments — not a UI | `on-session-start.mjs` reads staged memory files (research_brief, execution_context, agent_handoff) → **markdown to stdout** (no JSON wrapper needed), 5-min TTL cache to skip on resume | `PostToolUse Write` → `on-stage-transition.mjs` detects pipeline stage transitions | `.claude-plugin/marketplace.json` + `.agents/plugins/marketplace.json` (multi-harness: Claude Code + Codex) | **HIGH** | Closest workflow analog; experiment-driver agent = template for explore-train/retrain-from-sop; markdown memory files + decision_log/experiment_ledger; `/omp:setup` registers SessionStart into project `.claude/settings.json` |
| **obra/superpowers** (prior, confirmed) | Core skills lib: TDD, debugging, planning | 14 flat `skills/<name>/SKILL.md` + optional `references/scripts` | SessionStart only (sync, `additionalContext`) | No | `session-start` script: read bootstrap SKILL.md → bash JSON-escape → wrap in `<EXTREMELY_IMPORTANT>` → `hookSpecificOutput.additionalContext` | (none) | `marketplace.json` `source:"./"` (root) | **HIGH** | Hook infra skeleton (prior rec stands); SDO descriptions; intent-style SKILL.md |
| **jarrodwatts/claude-hud** (25k★) | Real-time HUD: context %, tools, agents, todos | No skills; `commands/` + compiled `src/` (TS) | None — uses `statusLine` setting (config-driven) | No sidecar — renders JS **into Claude Code's own statusline** | n/a | n/a | `marketplace add jarrodwatts/claude-hud` | **MED** | The *alternative* to a browser sidecar: render into Claude Code's statusline surface. MLagent chose browser UI; statusline could be a Stage-2 lightweight fallback. Linux `/tmp` tmpfs install bug (#14799) is a real pitfall. |
| **anthropics/claude-plugins-official / skill-creator** | Meta-skill: draft→test→eval→rewrite skills | `plugins/skill-creator/{.claude-plugin, skills/skill-creator/{SKILL.md, scripts, references, assets, agents, eval-viewer}}` | (none in plugin) | No | n/a | n/a | Official curated marketplace; `source:{source:"git-subdir",url,path,ref,sha}` (pinned) | **MED** | Canonical "skill bundles scripts/ + references/ + assets/ + eval-viewer/" layout; the draft→eval→rewrite loop is the inner loop for `instance-to-sop` |
| **anthropics/skills** (canonical skills-as-procedures) | 17 reference skills (pdf, pptx, mcp-builder, skill-creator…) | `skills/<name>/SKILL.md` + scripts/references | n/a | No | n/a | n/a | Reference repo | **MED** | Canonical progressive-disclosure SKILL.md; skills-as-procedures (scripts do deterministic work, SKILL.md holds judgment) |
| **anthropics/claude-code/plugins/{plugin-dev, hookify}** | Plugin-dev meta-skill; hook generator | skills + utils | hookify generates matchers/utils | No | n/a | n/a | bundled | **LOW–MED** | hookify's `matchers/`+`utils/` separation |
| **ananddtyagi/cc-marketplace** | Community marketplace | per-plugin | per-plugin | per-plugin | per-plugin | per-plugin | `marketplace.json` `source:"./plugins/<name>"` + category/keywords/homepage | **LOW** (infra) | Marketplace.json field set; local-subdir pattern at scale |
| **trailofbits/skills-curated** | Curated, security-vetted marketplace | skills | (varies) | (varies) | (varies) | (varies) | curated marketplace | **LOW** | "Curated/vetted" positioning |
| **hashicorp/agent-skills** | Multi-skill plugin (Terraform/Vault/Consul) | skills + agents | (varies) | (varies) | (varies) | (varies) | vendor marketplace | **LOW** | Enterprise multi-skill-plugin precedent |

**Excluded (tangential):** `wasp-lang/open-saas` (SaaS boilerplate); single-purpose domain plugins (`cavekit`, `cartographer`, `mckinsey-pptx`, `fablize`, etc. — no sidecar/hook/SOP patterns needed); `awesome-claude-code` (discovery list, not a pattern source); `claude-code-lsps` (niche).

## 2. Notable ecosystem findings (2025–2026)

**Active marketplaces:** `anthropics/claude-plugins-official` (31k★, pinned `git-subdir`+sha); `obra/superpowers-marketplace` (1.1k★, `source:"./"`); community `ananddtyagi/cc-marketplace`, `trailofbits/skills-curated`, `claude-night-market`. Pattern: any repo with `.claude-plugin/marketplace.json` is installable via `/plugin marketplace add <owner>/<repo>`.

**Canonical plugin structure (confirmed):** `.claude-plugin/plugin.json` (manifest) + `skills/<name>/SKILL.md` + `hooks/hooks.json` + `commands/*.md` + `agents/*.md` + `bin/` (auto-PATH) + optional `scripts/`, `.mcp.json`, `settings.json`. Multi-skill uses `skills/`; skills namespaced `/plugin-name:skill-name`.

**The `Setup` hook event (NEW):** runs once on plugin install/enable — claude-smart uses it (300s timeout) to build the dashboard + prep venv. Right place to build the UI / `pip install` deps once, not per SessionStart.

**`reloadSkills` + `watchPaths` (NEW, dynamic-skill bridge):** SessionStart accepts `hookSpecificOutput.reloadSkills:true` + `watchPaths` → forces Claude Code to **re-scan skill directories**. Mechanism to surface newly-written skills at runtime (§3e).

**Skill discovery locations:** plugin (`<plugin>/skills/`, static at install), personal (`~/.claude/skills/`, cross-project), project (`.claude/skills/`, per-repo). Only the latter two are writable at runtime.

**Gotchas (verified):**
1. **Local-`source` path bug** (#11243, #11278, #29485): relative `source` (`"."`, `"./plugin"`) gets mis-resolved (appended to full marketplace.json path incl. filename). Works only when marketplace added as **local path/git repo** (full tree present); **breaks for URL-fetched marketplaces**. superpowers/claude-smart work because users add the repo, not a URL. → MLagent: document "add the repo, not a URL" or ship pinned `git-subdir`.
2. **`async:true` silently drops SessionStart `additionalContext`** (superpowers #444) — SessionStart must be **synchronous**.
3. **Sidecar lifecycle: `Stop` vs `SessionEnd`** — `Stop` fires after *every* turn (frequent, would thrash a UI); `SessionEnd` fires on real termination (`/clear`/`/resume`/exit) but has **default 1.5s timeout** (`CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS` overrides). claude-smart tears down on SessionEnd, **only if opt-in** (`CLAUDE_SMART_DASHBOARD_STOP_ON_END=1`) — default dashboard **stays alive across sessions**. **Contradicts spec §5.1/§6.2 ("Stop → ui stop")** — see §3d.
4. **Cross-platform detached spawn** (claude-smart `spawn_detached`): Linux `setsid`, macOS `python3 os.setsid + execvp`, Windows `nohup`. Teardown: POSIX signal the process group; Windows `taskkill /T /F /PID`.
5. **Port-ownership verification** — probe `/api/health` for a **marker header** before binding/killing (never clobber a foreign process on the same port).
6. **`${CLAUDE_PLUGIN_ROOT}` can be unset** — fall back to `$HOME/.claude/plugins/marketplaces/<name>/plugin`.
7. **Linux `/tmp` tmpfs install failure** (#14799): `EXDEV` — fix `TMPDIR=~/.cache/tmp`.
8. **PostToolUse cannot block** (`exit 2` only surfaces stderr after the tool ran) — only `additionalContext`/`updatedToolOutput`. Bounds raw_memory capture to *nudging*, not *gating* (consistent with spec Q3).

## 3. Concrete v0.3 adapter recommendations

### (a) The 5 skills' SKILL.md structure + bootstrap orchestration
Structure (superpowers SDO + skill-creator script-bundling + Oh-my-paper experiment-driver):
```
skills/<name>/{SKILL.md, scripts/, references/}
```
- **Descriptions:** strict SDO — only "Use when …" triggers, never the workflow (anti-pattern: workflow-in-description lets the model shortcut the body). e.g. `explore-train`: `Use when the user wants to explore a dataset, build a baseline, or run a training experiment — before writing training scripts.`
- Every skill needs `## When NOT to use`.
- **`mlagent-bootstrap`** is special: **not invoked by the model but injected wholesale by SessionStart** (superpowers `using-superpowers`). Body = workflow map (when each of the other 4 skills fires) + raw_memory rule + manifest rule + current SOP-library status. Wrap in `<EXTREMELY_IMPORTANT>`; ≤3.5k chars (10k `additionalContext` cap minus memory summary).
- **Bootstrap orchestrates declaratively** (frames the 5-skill state machine); each skill self-selects via description. Cite **Oh-my-paper Conductor** (role-selection → staged pipeline with auto-sync rule) + **superpowers using-superpowers**.

### (b) SessionStart hook: launch UI sidecar + inject context
Model on **claude-smart** (`plugin/scripts/{backend,dashboard}-service.sh`):
```jsonc
"SessionStart": [{
  "matcher": "startup|resume|clear|compact",
  "hooks": [
    { "type":"command", "command":"${CLAUDE_PLUGIN_ROOT}/hooks/session-start", "timeout":10 },     // inject bootstrap+memory state (SYNC! no async)
    { "type":"command", "command":"${CLAUDE_PLUGIN_ROOT}/bin/mlagent ui start", "timeout":60 }     // detached sidecar launch, last
  ]
}]
```
- `bin/mlagent ui start`: probe `http://127.0.0.1:<port>/api/health` for MLagent marker header; if not ours, **spawn detached** (per-OS) writing PID to `~/.mlagent/ui.pid` + log; poll `/health` ≤5s; **return immediately regardless** (emit `additionalContext` with URL or "unavailable, see log" — never block, spec D1/P4).
- Injection content: read `skills/mlagent-bootstrap/SKILL.md` + short memory-state summary → JSON-escape → `additionalContext`. Oh-my-paper **TTL cache** (skip re-inject if <5 min old) avoids spam on rapid resume.
- **Build UI once via `Setup` hook** (300s timeout → `mlagent install` builds frontend + venv) — keeps SessionStart fast.

### (c) PostToolUse capture granularity (conservative)
Matches spec §6.2 + claude-smart/Oh-my-paper:
- matcher `Write|Edit|Bash`, `exit 0` always (cannot block).
- Extract via `jq`: `tool_name`, `tool_input.file_path`, `tool_input.command`. **Do not** store `tool_response`/diffs — append one-line TSV to `project_memory/raw_memory/drafts.tsv`.
- **Nudge, don't gate:** training commands (`grep -qE 'python.*train|torchrun|accelerate'`) → `additionalContext`: "tee output to `runs/<ts>/log.txt`". `Write|Edit` on `*.py` → "update `<script>.manifest.yaml` if entrypoint/inputs changed."
- Consider **`PostToolBatch`** (NEW event) for one summary per parallel batch — saves tokens.

### (d) Stop hook: teardown + distill trigger
**Recommend changing spec from "Stop → `ui stop`" to "`SessionEnd` → `ui stop`; `Stop` → distill only."** (claude-smart rationale):
- **`Stop` fires every turn** — killing/restarting UI each turn is wrong; Stop's 30s budget is for distill/summarize, not process mgmt.
- **`SessionEnd` is the real teardown**, but default **1.5s timeout** too short → set `timeout:10` on `ui stop`.
- **Long-lived-by-default** (claude-smart): UI survives across sessions; tear down on SessionEnd only (also survives Stop thrash). Expose `MLAGENT_UI_STOP_ON_END=1` for strict per-session.
- **Stop = session summary + distill trigger:** run `bin/mlagent distill --if-due` as **`async:true`** command hook (async fine for Stop; the #444 drop only affects SessionStart). Background; result lands as `additionalContext` next turn. Low-confidence never auto-promotes (spec Q4).

### (e) skill_library versions as Claude Code skills — discoverable/invokable
**Hard constraint (verified):** a plugin's `skills/` dir is **static at install** — can't drop new skills into an installed plugin. BUT skills are also discovered from **project `.claude/skills/`** and **`~/.claude/skills/`**, and SessionStart accepts **`reloadSkills:true`**.

**Bridge (recommended):** `instance-to-sop` → `approve-sop` writes an approved SOP version as a **real skill** to project `.claude/skills/<sop>-vXXX/SKILL.md` (+ `scripts/`), not just `skill_library/`:
- `skill_library/<sop>/vXXX/` = **human-readable source-of-truth archive** (YAML metadata, evidence, performance).
- `.claude/skills/<sop>-vXXX/` = **thin invocable projection** (SKILL.md = SOP procedure + pointer back to skill_library + `scripts/` symlinked/copied). The skill-as-procedure pattern.
- A SessionStart (or PostToolUse-after-approve) hook emits `{hookSpecificOutput:{hookEventName:"SessionStart", reloadSkills:true}}` → new SOP-skill immediately callable as `/<sop>-vXXX` without restart.
- `registry.yaml` tracks `current`/`superseded`; only `current`'s projection belongs in `.claude/skills/` — superseding swaps the file + re-`reloadSkills`. Mirrors claude-smart **CURRENT→ARCHIVED** skill status lifecycle.

**Limits:** `reloadSkills` only on a SessionStart-context hook (can't hot-swap mid-turn). SOP approved mid-session → invocable **next SessionStart/`/clear`**. For immediate use, `retrain-from-sop` reads SOPs **directly from `skill_library/`** (no router needed) — which spec §6.1 already does.

### (f) marketplace.json + distribution
Ship as **monorepo + local-subdir marketplace** (claude-smart `source:"./plugin"`):
```jsonc
// .claude-plugin/marketplace.json
{
  "name": "mlagent",
  "owner": { "name": "..." },
  "metadata": { "description": "MLagent — Claude-Code-native ML R&D visibility + Skill-SOP library", "version": "0.1.0" },
  "plugins": [{
    "name": "mlagent", "version": "0.1.0",
    "source": "./mlagent-plugin",       // works ONLY when repo added, NOT URL-fetched (gotcha #1)
    "description": "...", "category": "machine-learning",
    "keywords": ["ml","training","skills","hooks","sop"], "homepage": "..."
  }]
}
```
- **Install:** `/plugin marketplace add <owner>/MLagent_v0.3` (clone repo) → `/plugin install mlagent` → restart. **Document "add the repo, not a URL."**
- **Pinned distribution:** official `git-subdir` source (`{source:"git-subdir",url,path,ref,sha}`) — works with URL fetches + pins commit.
- **Local dev:** `/plugin marketplace add ./MLagent_v0.3` + `/plugin install mlagent` + `/reload-plugins` after edits.
- **UI in plugin:** put `ui/` (FastAPI + frontend build) **inside the plugin dir** (spec §9); `Setup` hook builds it once. claude-smart ships a full Next.js app inside `plugin/dashboard/` — precedent.

## 4. Ecosystem gotchas to design around
1. **Don't tear down UI on `Stop`** (every turn → thrash). Use `SessionEnd` + explicit `timeout:10`. Consider long-lived-by-default.
2. **SessionStart must be synchronous** (`async:true` drops `additionalContext`, #444).
3. **Sidecar launch detached + return immediately** (per-OS setsid/os.setsid/nohup; PID file; health-probe with marker header; never block — degrade gracefully, D1).
4. **`${CLAUDE_PLUGIN_ROOT}` may be unset** — fall back to marketplaces install path.
5. **Relative `source` breaks URL-fetched marketplaces** — document repo-add; or use `git-subdir`.
6. **`additionalContext` 10k char cap** — bootstrap + memory summary must fit; spill to file, inject "preview + path" (Oh-my-paper TTL-cache).
7. **PostToolUse cannot gate** — design capture as nudging/recording (aligns spec Q3).
8. **Skills not dynamically addable to an installed plugin** — bridge via project `.claude/skills/` + `reloadSkills` (§3e); `retrain-from-sop` reads SOPs directly.
9. **Build heavy artifacts (UI, venv) in `Setup`, not SessionStart** (300s vs 10–60s).
10. **Linux `/tmp` tmpfs** breaks install (#14799) — `TMPDIR` workaround.
11. **`/clear`/`/resume` re-fire SessionStart** — make injection idempotent (TTL cache); UI start idempotent (probe-before-spawn).

## Sources
**Primary (HIGH):** [ReflexioAI/claude-smart](https://github.com/ReflexioAI/claude-smart) ([ARCHITECTURE.md](https://github.com/ReflexioAI/claude-smart/blob/main/ARCHITECTURE.md), [hooks.json](https://github.com/ReflexioAI/claude-smart/blob/main/plugin/hooks/hooks.json), [dashboard-service.sh](https://github.com/ReflexioAI/claude-smart/blob/main/plugin/scripts/dashboard-service.sh), [backend-service.sh](https://github.com/ReflexioAI/claude-smart/blob/main/plugin/scripts/backend-service.sh)) · [LigphiDonk/Oh-my-paper](https://github.com/LigphiDonk/Oh--paper) ([README](https://github.com/LigphiDonk/Oh-my--paper/blob/main/README.md), [hooks.json](https://github.com/LigphiDonk/Oh-my--paper/blob/main/plugins/oh-my-paper/hooks/hooks.json), [on-session-start.mjs](https://github.com/LigphiDonk/Oh-my--paper/blob/main/plugins/oh-my-paper/scripts/on-session-start.mjs), [experiment-driver agent](https://github.com/LigphiDonk/Oh-my--paper/blob/main/plugins/oh-my-paper/agents/experiment-driver.md), [sidecar MCP runner](https://github.com/LigphiDonk/Oh-my--paper/blob/main/sidecar/runners/experiment-mcp-server.mjs)) · [obra/superpowers](https://github.com/obra/superpowers) ([marketplace.json](https://github.com/obra/superpowers/blob/main/.claude-plugin/marketplace.json))
**Official/canonical:** [anthropics/claude-plugins-official](https://github.com/anthropics/claude-plugins-official) ([skill-creator](https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator)) · [anthropics/skills](https://github.com/anthropics/skills) · [Hooks ref](https://code.claude.com/docs/en/hooks) (verified: `reloadSkills`, `watchPaths`, PostToolUse non-blocking, SessionEnd 1.5s default) · [Skills doc](https://code.claude.com/docs/en/skills) (personal/project/plugin discovery) · [Plugins ref](https://code.claude.com/docs/en/plugins-reference) · [Marketplaces](https://code.claude.com/docs/en/plugin-marketplaces)
**Gotchas/issues:** local-source path bug [#11243](https://github.com/anthropics/claude-code/issues/11243)/[#11278](https://github.com/anthropics/claude-code/issues/11278)/[#29485](https://github.com/anthropics/claude-code/issues/29485) · async drops SessionStart [superpowers #444](https://github.com/obra/superpowers/issues/444) · Linux /tmp tmpfs [#14799](https://github.com/anthropics/claude-code/issues/14799)
**Context (MED/LOW):** [jarrodwatts/claude-hud](https://github.com/jarrodwatts/claude-hud) (statusline alternative) · [ananddtyagi/cc-marketplace](https://github.com/ananddtyagi/cc-marketplace) · [hesreallyhim/awesome-claude-code](https://github.com/hesreallyhim/awesome-claude-code)

**Uncertainties flagged:** (1) Whether `reloadSkills` re-scans **project** `.claude/skills/` or only plugin skills — docs say it reloads skills generally; inferred project skills included but no explicit statement (test before relying). (2) Exact `Setup` hook trigger conditions (install-only vs enable/update) — claude-smart treats it as install/bootstrap; verify against `plugins-reference`. (3) claude-smart's `spawn_detached` helper source in `plugin/scripts/_lib.sh` (referenced, not read in full) — per-OS recipe from inline comments in `dashboard-service.sh`.
