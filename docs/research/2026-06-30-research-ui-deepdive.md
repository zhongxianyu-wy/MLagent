# MLagent v0.3 UI Subsystem — GitHub Research: Interactive UIs for Developer/ML-Agent Tools

> Backref: [redesign spec](../superpowers/specs/2026-06-26-mlagent-redesign-spec.md) · Date: 2026-06-30 · Branch: `v0.3`
> Design inspiration only; stack already decided (FastAPI backend + independent lightweight frontend, file-first, local single-user, UI = view-layer, P4). Prior lighter research (`2026-06-26-ui-panels.md`, `2026-06-26-tech-stack.md`) covered marimo/Quarto/logdy/MLflow/Aim/HTMX/Alpine/CM6. This sweep goes **broader and deeper**, confirming prior picks with primary-source code reads + surfacing newer/lighter 2025–2026 options.

## 1. Comparison table

| Project | What it visualizes | Live-update mechanism | Structured-view approach | Log/metrics handling | Write-back? | Local lifecycle | Stack / weight | Relevance | Borrowable pattern |
|---|---|---|---|---|---|---|---|---|---|
| **gradio-app/trackio** ⭐1555 | Experiment runs, metrics, media, tables, alerts; **"built for humans and AI agents"** | **`setInterval` polling 1000ms local / 3500ms HF-Space**, paused when tab hidden or rate-limited (`lib/hostPolling.js`); SSE exists in `asgi_app.py` but only for one-shot Gradio API completion, **not** live metrics | Run table + pinned metrics tabs (Gradio-inspired) | REST `/api/*`; metrics in **SQLite** (Parquet freeze) | Yes (mutation endpoints, write-token) | `trackio show` / `trackio.show()` → uvicorn in thread, port-seek 7860+100, health-check `/version`, `127.0.0.1` | Python backend + **Svelte 5** frontend; **forkable**, "replace UI without forking backend" (frontend dir only needs `index.html`) | **HIGH** | "Agent-friendly local dashboard" template; swappable frontend; SQLite metrics; polling-not-SSE for refresh; CLI query `--sql` |
| **SwanHubX/SwanLab** + **SwanLab-Dashboard** ⭐4024 / ⭐26 | Training metrics (line/media/3D/scatter/box/heatmap…), offline board via `swanlab watch` | REST + Vue **polling** (no WS/SSE in backend routers) | Run/experiment/tag/summary/chart REST routers (`experiment.py`) | `recent_log`, `tag_data`, `summary`, `charts` routers; SQLite | No (read-only board) | `swanlab watch` → FastAPI + StaticFiles serves bundled Vue | Python (swanboard, FastAPI) + **Vue**, built frontend bundled into `swanboard/template/` via `npm run build.release` | **HIGH** | **Exact "FastAPI backend + independent frontend" reference**; clean REST surface (experiment/tag/summary/log/chart) maps directly to our panels B+C; bundled-Vue-inside-pip pattern |
| **Arize-ai/phoenix** ⭐10341 | LLM traces/spans, evals, datasets, prompts (Claude Agent SDK integration) | OTel push + UI refresh; SPA served as static | Trace waterfall/span tree | SQL/ClickHouse/SQLite backend | Yes (datasets, playground) | `pip install arize-phoenix` → local server | Python (FastAPI/Starlette) + **Next.js**, built to `SERVER_DIR/static`, Vite `manifest.json`; heavy | **MED** (UI-inspiration; too heavy to import) | **`class Static(StaticFiles)` with index.html fallback** for serving built SPA from a pip package — the canonical bundling pattern; `dev_vite_port` dev-server fallback; explicit Claude-Agent-SDK + agent-cli angle |
| **logdyhq/logdy-core** ⭐2238 | Real-time log stream (`tail -f`), structured-log columns/parsers | **WebSocket** + **ring buffer**; `tail -f file \| logdy` | Auto-generated filters/columns from structured logs | Native ANSI/error handling; custom TS parsers | No | Single Go binary, embedded web UI on `:8080`, `nohup &` | Go (single binary, zero-dep) + embedded web UI | **MED** | "single binary + embedded web UI + tail -f" = our SessionStart-launched local process; ring buffer for high-freq logs; ANSI/error handling |
| **ploomber/sklearn-evaluation** ⭐467 | ML eval plots/tables, **HTML reports**, **SQLite experiment tracker**, notebook-output comparison | None (static/report) | `Table` (`to_html()`); `NotebookCollection` (compare notebook outputs side-by-side) | **`SQLiteTracker`**: `new()`→`log_dict()`, `recent(n)`, `query(code, as_frame=True)`→DataFrame | Yes (insert/upsert) | Library (no server) | Python (tabulate, pandas) — **very light** | **MED-HIGH** | `SQLiteTracker.query(...,as_frame=True)`→DataFrame→`to_html()` = zero-chart-dep metrics table + cross-run compare; `NotebookCollection` = the exact "compare runs/notebooks" UX; HTML-report injection |
| **FEMessage/log-viewer** ⭐119 | Terminal logs in browser (Docker logs) | WebSocket | Stream lines | **ANSI escape-code processing**; special-char handling | No | Node | Node/React | **MED** | ANSI-escape rendering in browser (our panel B ANSI/error handling) |
| **satyagraha/logviewer** ⭐64 | Tail log files in browser | **WebSocket** streams new lines | File picker → tail | Plain tail | No | Java/Node | Java + WS | LOW-MED | Minimal WS-tail data-flow reference (we'll likely use SSE/polling) |
| **marimo-team/marimo** ⭐21632 | Reactive notebook; cells as dataflow graph | Reactive re-run on cell edit (static-analysis deps) | **Dataflow graph** of cells; code+output per cell | Cell outputs | Yes (edit cells) | `marimo edit` → local server | Python runtime + built JS frontend (served from package) | **MED** (concept) | "Input changed → dependents re-render" = our manifest-driven panel A (but our dep-graph is the manifest, far simpler than marimo's static analysis). Don't import (Pyodide/WASM runtime). |
| **amakelov/mandala** ⭐539 | Experiments as **ComputationFrame** (code → high-level graph of variables/ops → queryable dataframe) | None (memoization-based) | **Semantic computation graph** over raw code; restrict by function versions | `query` → dataframe | Yes (memoized) | Library | Python, graphviz for viz | **MED** (concept) | ComputationFrame = strongest conceptual model for "semantic step view over a script" (panel A): turn code into a graph of named operations + params. Our manifest is the hand-authored version. |
| **openlit/openlit** ⭐2563 | OTel-native LLM observability, exceptions dashboard, evals | OTel SDK → Collector → ClickHouse; UI pulls | Trace/span + rule-engine | Exceptions monitoring dashboard | — | Docker self-host | Go/Python SDKs + UI pulling ClickHouse | LOW | OTel-heavy; not our model (file-first, no collector). Skip. |
| Python-native UI frameworks (Gradio ⭐43039, Taipy ⭐19252, Reflex ⭐28617, Mesop ⭐6593, Flet ⭐16283, NiceGUI, Streamlit ⭐45114) | "Build UI in Python" |各自的 ws/重连 |各自 |各自 |各自 |各自 | Pure-Python UI | **LOW** (deliberately excluded) | The **alternative paradigm we rejected** per Q1/D4 (we want FastAPI + independent frontend, not Python-generates-UI). Documenting the non-choice. |

## 2. NEW / lighter 2025–2026 options worth considering over the obvious ones

- **`gradio-app/trackio` (HuggingFace, 2025, ⭐1555, updated 2026-06-30)** — the single most on-target find. Explicitly *"built by Hugging Face for humans and AI agents"*, **local-first**, **SQLite-backed**, wandb-compatible API, **forkable** (Python backend / Svelte 5 frontend, swappable via `--frontend` flag or `frontend_dir`), launched by `trackio show`. Has its own `.agents/` dir + `CLAUDE.md`. Essentially a productionized version of our exact niche. → **Read first when building.** Even if we don't depend on it, mirror its architecture.
- **SwanLab offline board (`pip install 'swanlab[dashboard]'` → `swanlab watch`)** — Chinese-origin, the **closest architectural twin** (FastAPI backend + independent Vue frontend, frontend bundled into pip package, launched by `watch`). Note: SwanBoard is being deprecated into `swanlab-core` — read for pattern, not for depending.
- **`ploomber/sklearn-evaluation` `SQLiteTracker`** — if you want the metrics table + cross-run compare to be **SQL-queryable** (matches spec's SQLite/FTS5 mention) with zero chart deps (`query(..., as_frame=True)` → `to_html()`), the lightest reference.
- **`mandala` ComputationFrame** — newest conceptual model (2024–2025) for "semantic graph over code"; relevant inspiration for panel A's manifest-driven structure (a manifest is a hand-authored ComputationFrame).

(The obvious heavyweights — MLflow, W&B-local, Aim, Langfuse, Phoenix — remain UI-design references only. None lighter than the above for local-single-user file-first constraints.)

## 3. Concrete v0.3 UI recommendations

### (a) Backend file-watch + push — recommend SSE, polling as pragmatic default
Two leading lightweight local dashboards (trackio, SwanBoard) both ship **plain REST polling** (trackio: 1000ms, paused on hidden tab / rate-limit; SwanBoard: Vue polling) and it works great for SQLite/file-backed data. But for our panel B (live `log.txt` tail) polling is wasteful and SSE fits better; FastAPI ships native `EventSourceResponse` (0.135+) with auto keep-alive ping + `Last-Event-ID` resume. **Recommendation: SSE for log tail + manifest/code change push (server→browser, one-way); plain REST `PUT` for write-back.** Do **not** use WebSocket — write-back is a simple PUT, no bidirectional need (confirmed across trackio/SwanBoard/FEMessage). Polling (trackio's 1000ms `hostPolling.js`) is the documented graceful-degrade fallback.

### (b) Manifest-driven structured script panel (Panel A) — Quarto code-annotation form + mandala ComputationFrame concept; marimo for reactive re-render philosophy
- **Form factor:** Quarto code-annotation (numbered line-annotations + step explainer beside/under code) — exact UI paradigm.
- **Conceptual model:** mandala's ComputationFrame (code → graph of named operations + params → queryable) is the strongest mental model; **our `<script>.manifest.yaml` is a hand-authored ComputationFrame** (semantic steps: feature-eng/data-split/model/train/eval/save, each with purpose + location + key_params).
- **Re-render:** marimo's "input changed → dependents re-render", but our dependency graph is the manifest (far simpler than marimo's static analysis) — on manifest/code change (watchfiles), FastAPI re-reads manifest + slices code by line-range → SSE push → frontend re-renders just that step.
- **Code highlighting:** highlight.js (CDN, zero-build); do **not** pull in Shiki/Monaco.

### (c) Log tail panel (Panel B) — ring buffer + ANSI handling + sticky-to-bottom
- **Backend:** watchfiles `awatch` on `runs/<id>/log.txt` → SSE push raw lines (uvicorn[standard] pulls watchfiles for free).
- **ANSI + error highlight:** borrow FEMessage/log-viewer's ANSI-escape processing; regex `ERROR|Traceback|FAILED|AssertionError` → error class.
- **High-frequency:** logdy's **ring buffer** pattern; batch updates (~16ms) before DOM write; sticky-to-bottom with "pause on user scroll-up, resume at bottom" (React Virtuoso `followOutput` issue #317 is the canonical warning if we ever go React). With Alpine/no-build, a simple cap-last-N ring buffer + `overflow-y:auto` suffices for local log volume.

### (d) Metrics table + cross-run compare (Panel C) — `SQLiteTracker.query(as_frame=True)→to_html()` + MLflow/Aim UI design
- **Lightest implementation:** mirror sklearn-evaluation's `SQLiteTracker` — store `metrics.json` rows in SQLite, `query(..., as_frame=True)` → pandas DataFrame → `to_html()` = zero-chart-dep table. Cross-run compare = `NotebookCollection`-style side-by-side (runs as rows, params+metrics as columns).
- **UI design borrow:** MLflow Table View (run_id | key param | key metric) + Aim's "pin frequently-used metric" — UI-design-only, no dependency.
- **Charts later:** Chart.js CDN (~200KB) for metric-over-step lines; MVP stays pure `<table>`.

### (e) Write-back intervention UX (edit → file → flag)
- **Editor:** CodeMirror 6 via `esm.sh` (no build); Sourcegraph's Monaco→CM6 migration validates the choice; Monaco too heavy.
- **Write-back:** editor onBlur/Ctrl+S → `PUT /api/file?path=…` → FastAPI writes file (**path-traversal guard**) + appends a `human_interventions` record to raw_memory (or sets `needs_rereview`). Monaco/CM don't do file I/O — we implement it (microsoft/monaco-editor#356).
- **Pattern confirmation:** trackio has real mutation endpoints with write-token; SwanBoard is read-only by design. Ours sits between — read-mostly with explicit intervention write-back (spec D3).

### (f) Frontend choice + bundling inside a Claude Code plugin — Alpine.js (no-build) for MVP; if a build step is acceptable, mirror trackio/SwanBoard/Phoenix's "build-at-wheel-time"
The most important new finding. Three production projects solve **"ship a built frontend inside a Python package"** identically — strong consensus:
- **trackio** (`hatch_build.py`): at wheel-build time runs `npm ci && npm run build` → output to `trackio/frontend/dist/index.html`; `SKIP_FRONTEND_BUILD`/`TRACKIO_FRONTEND_FORCE_REBUILD` env vars. Runtime serves `dist/`. **Graceful degrade:** `frontend_server.py` ships a **minimal starter** (just needs an `index.html`) — if the real frontend dir is missing/invalid, falls back to starter, keeping `/api/*` backend intact. **Exactly** our P4 "UI is view-layer, system works without it."
- **SwanBoard** (`npm run build.release` → `swanboard/template/`) — same, Vue → `template/`, served by FastAPI `StaticFiles`.
- **Phoenix** (`src/phoenix/server/app.py`): `class Static(StaticFiles)` subclass with **`index.html` fallback on 404** for SPA routing; `static_dir = SERVER_DIR/"static"`; `has_built_ui = (static_dir/".vite/manifest.json").is_file()`; in dev points at `dev_vite_port: 5173`.

**Recommendation for MLagent:**
- **MVP (no Node toolchain, fastest):** Alpine.js + native ESM (import map) + highlight.js, all from CDN or pre-downloaded into `assets/` for offline — a single `index.html` + a few JS files served by FastAPI `StaticFiles`. Matches trackio's "frontend dir only needs an `index.html`" minimal contract.
- **If interactions outgrow Alpine:** adopt **trackio/Phoenix build-at-wheel-time** — build hook runs `npm run build` → `ui/dist/`, shipped inside the plugin; serve via a `Static(StaticFiles)` subclass with `index.html`-on-404 fallback (copy Phoenix's ~15-line class). Keep a minimal starter `index.html` as graceful-degrade fallback (copy trackio's `frontend_server.py`).
- **Plugin layout:** `ui/dist/` (built) + `ui/static/` (fallback starter) inside the plugin dir; launched as localhost by SessionStart hook.

### (g) Graceful degrade when UI can't start
- Spec mandates (P4, §5.1): UI failure non-fatal; hook degrades to terminal-only memory-status prompt.
- **Concrete patterns borrowed:**
  - **trackio's `frontend_server.py` minimal-starter fallback** — backend `/api/*` stays up even if rich frontend missing; only `index.html` required. Mirror: if `ui/dist/` absent/corrupt, serve a 1-file starter showing memory status + raw file links.
  - **Phoenix's `has_built_ui` check** — detect missing built UI, fall back gracefully.
  - **Local lifecycle (trackio `launch.py`):** SessionStart hook → `nohup … & disown` (return immediately), port-seek a range, write port to file, `webbrowser.open`; Stop → `SIGTERM`/`pkill` (SessionEnd default 1.5s → keep shutdown fast). trackio's Gradio-derived port-seek (try 100 ports from 7860, health-check `/version`) is the production reference.

## 4. Borrow vs build notes

**Borrow (patterns/code, not dependencies — stack decided):**
- **Phoenix's `Static(StaticFiles)` index.html-fallback class** (~15 lines) — copy verbatim for serving a built SPA.
- **trackio's `frontend_server.py` minimal-starter + live-reload** — graceful-degrade fallback concept.
- **trackio's `hostPolling.js`** (1000ms, pause-on-hidden, rate-limit cooldown) — if we add polling.
- **sklearn-evaluation `SQLiteTracker.query(as_frame=True)` + `Table.to_html()`** — SQL→DataFrame→HTML-table for panel C (zero chart deps).
- **FEMessage/log-viewer ANSI processing** — panel B.
- **Quarto code-annotation + mandala ComputationFrame** — form factor + mental model for panel A.
- **MLflow Table View + Aim pin** — UI design for panel C.
- **trackio `launch.py` port-seek + health-check** — local-launch lifecycle.

**Build fresh (specific to file-first / manifest-driven / Claude-Code-hook):**
- Manifest-driven panel A renderer (no project does exactly "read `<script>.manifest.yaml` + slice code by line-range + render semantic steps").
- `human_interventions` write-back → raw_memory-flag wiring (spec D3).
- The watchdog/SSE bridge for our file contract (`manifest.yaml` + `<script>.py` + `runs/<id>/log.txt` + `metrics.json`).
- SessionStart/Stop hook glue (Claude-Code-specific).

**Don't import (excluded):** MLflow / W&B-local / Aim / Langfuse / Phoenix-as-dep (too heavy, server/DB-centric, not file-first; UI-design only). Gradio / Streamlit / Taipy / Reflex / Mesop / Flet / NiceGUI ("Python builds UI", rejected per Q1/D4). marimo / Streamsync runtime (full runtimes, wrong shape). OpenLit (OTel-collector-based).

## 5. Sources

**Authoritative spec & prior research (read first):** `/Volumes/exp/project/MLagent_v0.3/docs/superpowers/specs/2026-06-26-mlagent-redesign-spec.md` (§3, §5, §8.4, §11–12); `…/research/2026-06-26-ui-panels.md`, `…/2026-06-26-tech-stack.md`.

**Experiment-tracking / agent dashboards (HIGH):**
- trackio: https://github.com/gradio-app/trackio · `trackio/frontend_server.py` (live-reload polling + minimal starter) · `trackio/frontend/src/lib/hostPolling.js` · `trackio/launch.py` (port-seek + health-check) · `trackio/asgi_app.py` (SSE) · `hatch_build.py` (build-frontend-at-wheel-time) · docs https://huggingface.co/docs/trackio
- SwanLab: https://github.com/SwanHubX/SwanLab · SwanBoard https://github.com/SwanHubX/SwanLab-Dashboard (`swanboard/app.py` StaticFiles, `swanboard/router/experiment.py` REST, `npm run build.release` → `template/`) · offline-board docs https://docs.swanlab.cn/guide_cloud/offline-board.html
- sklearn-evaluation: https://github.com/ploomber/sklearn-evaluation · `src/sklearn_evaluation/tracker.py` (`SQLiteTracker.query(as_frame=True)`) · `src/sklearn_evaluation/table.py` (`Table.to_html()`)
- mandala: https://github.com/amakelov/mandala · ComputationFrame blog https://amakelov.github.io/mandala/blog/01_cf/

**Observability (MED — UI inspiration, too heavy):** Phoenix: https://github.com/Arize-ai/phoenix · `src/phoenix/server/app.py` (`class Static(StaticFiles)` index.html fallback, `has_built_ui`, `dev_vite_port`) · Langfuse: https://github.com/langfuse/langfuse · OpenLit: https://github.com/openlit/openlit

**Live log viewers (MED):** logdy-core: https://github.com/logdyhq/logdy-core (single-binary + embedded web UI + ring buffer + WS) · FEMessage/log-viewer: https://github.com/FEMessage/log-viewer (ANSI-escape processing) · satyagraha/logviewer: https://github.com/satyagraha/logviewer (WS tail)

**Notebook / reactive / semantic-code (MED — concept):** marimo: https://github.com/marimo-team/marimo · dataflow https://marimo.io/blog/dataflow · Quarto code-annotation: https://quarto.org/docs/authoring/code-annotation.html

**File-watch / dev-tooling primitives (LOW — specced):** watchfiles: https://github.com/samuelcolvin/watchfiles · FastAPI SSE: https://fastapi.tiangolo.com/tutorial/server-sent-events/

**Python-native UI frameworks (LOW — deliberately excluded per Q1/D4):** Gradio https://github.com/gradio-app/gradio · Taipy https://github.com/Avaiga/taipy · Reflex https://github.com/reflex-dev/reflex · Mesop https://github.com/mesop-dev/mesop · Flet https://github.com/flet-dev/flet

**Uncertainties flagged:** trackio is very new (HuggingFace, 2025); architecture strongest match but API/serving details may shift — re-read `launch.py`/`frontend_server.py` at build time. SwanBoard being **deprecated** into swanlab-core — read for pattern only. Phoenix's `Static(StaticFiles)` class read but not its full build pipeline; `manifest.json`-detection + Vite-dev-fallback confirmed from `app.py` grep. `gh search repos` with multi-word queries + `--sort` returned empty in this environment; relied on direct `gh repo view` + single-term searches + README/code fetches, cross-confirmed. All URLs resolved via GitHub API (not fabricated).
