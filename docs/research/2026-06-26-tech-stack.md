# 实现技术栈调研

> Backref: [设计 spec](../superpowers/specs/2026-06-26-mlagent-redesign-spec.md) · Date: 2026-06-26 · 来源: GitHub + 官方文档（FastAPI / Claude Code / watchfiles / uv / Typer / CodeMirror）
>
> 对标已定决策：FastAPI 后端 + 独立前端、本地单用户、少依赖、Python 3.11（.venv）、UI 必须能从 Claude Code hook 可靠拉起。

## 一、技术栈推荐总表

| 层 | 推荐 | 备选 | 理由 | 依赖重量 |
|---|---|---|---|---|
| 后端框架 | **FastAPI**（已定） | Litestar | 官方 SSE 内置（`fastapi.sse`，0.135.0+）、Pydantic v2 原生、Starlette 同源 | 中（已含） |
| 实时推送 | **SSE（`EventSourceResponse`）** | WebSocket | 单向推送、浏览器原生 `EventSource` 自动重连、官方内置 keep-alive ping、断线 `Last-Event-ID` 续传。UI→后端回写走普通 REST，不需要 WS | 极轻（0 额外依赖） |
| 文件监听 | **watchfiles**（`awatch`） | watchdog / watchman | Rust 后端（notify）、Starlette/uvicorn 默认 reload 依赖、`awatch` 原生 async generator 与 FastAPI 事件循环无缝集成、跨平台 | 轻（Rust 扩展） |
| 前端框架 | **Alpine.js + 原生 ESM（import map）** | Vue 3 CDN / Preact+htm / HTMX | 单文件 `<script>` 即可（~15KB）、无 Node 工具链、Vue 式响应式语法、3 面板仪表盘完全够用。插件分发零 JS 构建 | 极轻 |
| 日志流式渲染 | **SSE 订阅 + 手写虚拟滚动 / `@tanstack/virtual`** | react-window | 本地日志量级（单 run 几 MB）用「环形缓冲 + 容器 scrollTop 帽 + 仅渲染可见行」足矣；错误行正则高亮 | 轻 |
| 性能表格/图表 | **MVP：纯 HTML `<table>`；后续：Chart.js** | lightweight-charts / ECharts | 跨 run 对比先做表格排序；要图时 Chart.js ~200KB 有 gauge 插件；lightweight-charts 不支持 gauge；ECharts 太重（~1MB） | 0（MVP） |
| 脚本结构渲染 | **highlight.js（CDN）+ 可折叠 `<details>`** | Shiki / Monaco readonly | 零构建：`<link>`+`<script>`+`hljs.highlightAll()`；Shiki 需异步 ESM 初始化较繁琐；Monaco 杀鸡用牛刀 | 极轻 |
| 编辑写回 | **CodeMirror 6（预构建 bundle 或 esm.sh）+ PUT** | Monaco | CM6 模块化、~130-200KB、移动端友好；Monaco 是整个 VS Code 引擎过重 | 中（仅编辑面板加载） |
| CLI 框架 | **Typer + Pydantic v2 + PyYAML** | Click / argparse | Typer 子命令+Rich 帮助、`[project.scripts]` 入口标准。注意 Typer 不原生支持 Pydantic 模型作参数类型，需回调内 `model_validate_json` | 轻 |
| 打包拉起 | **`type: command` hook（exec form）→ Python 子进程拉 uvicorn → 自动选空闲端口 → 写端口文件 → webbrowser.open** | systemd / nohup | SessionStart/Stop hook 可靠拉起/关闭本地 server；exec form `${CLAUDE_PLUGIN_ROOT}` 免引号转义；端口冲突用 `socket.bind(("",0))` | 0（uvicorn 已是后端依赖） |
| 依赖管理 | **pyproject.toml + uv** | pip-tools / poetry | `uv sync` 读 pyproject+uv.lock 一次性建环境；速度比 pip 快 10-100×；Astral 官方维护 | 轻（uv 单二进制） |

## 二、重点深度（每项 top 1-2 + 范式）

### 1. 后端 SSE 推送（核心）
**用 SSE，不用 WebSocket。** FastAPI 自 0.135.0 起官方内置 SSE（`fastapi.sse.EventSourceResponse`），无需 `sse-starlette`。文件变化是典型单向推送，浏览器 `EventSource` 原生自动重连、原生 `Last-Event-ID` 续传。
```python
from fastapi import FastAPI
from fastapi.sse import EventSourceResponse, ServerSentEvent
from watchfiles import awatch
app = FastAPI()

@app.get("/events/log", response_class=EventSourceResponse)
async def stream_log():
    async for changes in awatch("runs/current/log.txt"):
        for _, path in changes:
            with open(path) as f:
                line = f.readline()
            yield ServerSentEvent(raw_data=line, event="log", id=...)
```
官方内置 best practices（无需手写）：每 15s 自动发 `ping` 防 proxy 断连；自动 `Cache-Control: no-cache`；自动 `X-Accel-Buffering: no`。日志行用 `raw_data=`（不经 JSON 编码）。
文档：https://fastapi.tiangolo.com/tutorial/server-sent-events/

### 2. 文件监听（watchfiles）
watchfiles 是 samuelcolvin（Pydantic 作者）出品、Rust notify 后端，正是 uvicorn/Starlette `--reload` 的默认依赖（已隐式在依赖树里）。`awatch` 原生 async generator，与 FastAPI 事件循环零桥接成本。
```python
from watchfiles import awatch, DefaultFilter
class ManifestLogFilter(DefaultFilter):
    def __call__(self, change, path) -> bool:
        return path.endswith((".manifest.yaml", "log.txt", "metrics.json"))
async def watch_and_broadcast():
    async for changes in awatch("runs/", "scripts/", watch_filter=ManifestLogFilter(), stop_event=shutdown_event):
        await pubsub.publish(changes)
```
启动事件里 `asyncio.create_task(...)`，关闭时 `shutdown_event.set()`。`DefaultFilter` 默认忽略 `__pycache__`/`.git`/隐藏文件。
仓库：https://github.com/samuelcolvin/watchfiles · 文档 https://watchfiles.helpmanual.io/

### 3. 前端：Alpine.js 单文件 + import map（插件分发最省心）
React/Vue/Svelte 标准用法都要 Node + 打包器。Alpine.js 一个 `<script>`（~15KB gzipped）即可获得 Vue 式响应式（`x-data`/`x-show`/`x-for`/`x-text`），3 面板完全覆盖。
```html
<script type="module">
  import Alpine from 'https://esm.sh/alpinejs@3'
  window.Alpine = Alpine; Alpine.start()
</script>
<div x-data="{ logs: [], tail: true }">
  <ul><template x-for="line in logs.slice(-500)" :key="line.id">
    <li :class="line.level==='ERROR'?'text-red-600':''" x-text="line.text"></li>
  </template></ul>
</div>
<script>
  const es = new EventSource('/events/log')
  es.addEventListener('log', e => Alpine.store('app').logs.push(JSON.parse(e.data)))
</script>
```
备选：petite-vue（~6KB）或 Vue 3 CDN；Preact+htm 适合"想要 React 心智但不想要工具链"。
参考：https://github.com/alpinejs/alpine · https://github.com/vuejs/petite-vue

### 4. 日志流式渲染
- 后端：`awatch` log.txt → SSE 推 `raw_data` 行。
- 前端：`EventSource` 订阅 → 环形缓冲（cap 最近 N 行，如 5000）→ 仅渲染可视区。
- 虚拟滚动：本地量级不需要 react-window；用 `overflow-y:auto` + sticky-to-bottom flag（用户上滚暂停 auto-follow，回底恢复）。工业级用 `@tanstack/react-virtual`（~5KB，支持变高行）。
- 错误高亮：按 `level` 加 class；正则匹配 `ERROR|Traceback|FAILED` 上色。
- 参考：https://github.com/FEMessage/log-viewer

### 5. 性能表格 / 图表
MVP：纯 `<table>`（读 metrics.json 数组 → 列 run_id/accuracy/f1 → 表头排序，零图表依赖）。后续加图：Chart.js（~200KB，有 gauge 插件）。注意 lightweight-charts 虽最小（45KB）但不支持 gauge；ECharts 全量 ~1MB 过重。

### 6. 脚本结构渲染（highlight.js）
零构建是硬约束——Shiki 需 `async createHighlighter()` 初始化 + 打包器；highlight.js 只要 `<link>`+`<script>`+`hljs.highlightAll()`。
```html
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/github.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/highlight.js/11.9.0/highlight.min.js"></script>
<details><summary x-text="step.name"></summary>
  <pre><code class="language-python" x-text="step.code"></code></pre>
</details>
<script>hljs.highlightAll()</script>
```
manifest steps 渲染成可折叠步骤用原生 `<details>/<summary>`（零 JS）。**警告：别用 highlight.js 官网当 CDN**（被垃圾请求打爆），用 cdnjs/jsDelivr/unpkg。仓库：https://github.com/highlightjs/highlight.js

### 7. 编辑写回（CodeMirror 6 + PUT）
Monaco 是整个 VS Code 引擎（数 MB）；CodeMirror 6 模块化、~130-200KB。Sourcegraph 从 Monaco 迁到 CM6 可佐证。免构建方案：用社区预构建 bundle `cm6.bundle.js`（RPGillespie6/codemirror-quickstart）或从 `esm.sh/@codemirror/*` ESM CDN import。
```html
<script type="module">
  import { EditorState } from 'https://esm.sh/@codemirror/state'
  import { EditorView, basicSetup } from 'https://esm.sh/codemirror'
  import { python } from 'https://esm.sh/@codemirror/lang-python'
  const view = new EditorView({ state: EditorState.create({ doc: initial, extensions: [basicSetup, python()] }), parent: document.querySelector('#editor') })
  saveBtn.onclick = async () => {
    await fetch(`/api/file?path=${encodeURIComponent(p)}`, { method:'PUT', body: view.state.doc.toString() })
  }
</script>
```
后端 PUT：写文件 + 防路径穿越 + 打 human_intervention 标记。参考：https://codemirror.net/ · https://github.com/RPGillespie6/codemirror-quickstart · https://sourcegraph.com/blog/migrating-monaco-codemirror

### 8. CLI（Typer + Pydantic v2 + PyYAML）
**注意**：Typer 内部用 click 参数类型，**不原生支持 Pydantic 模型作函数参数类型标注**（issue #111 仍开放）。桥接：Typer 接收字符串/Path → 命令体内 `MyModel.model_validate_json(...)` 解析。
```python
import typer, yaml
from pathlib import Path
from pydantic import ValidationError
app = typer.Typer(no_args_is_help=True)

@app.command()
def validate(path: Path):
    raw = yaml.safe_load(path.read_text())
    try: SkillManifest.model_validate(raw)
    except ValidationError as e:
        typer.echo(str(e), err=True); raise typer.Exit(2)
    typer.echo(f"✓ {path} valid")
```
`[project.scripts] mlagent = "mlagent.cli:app"`。文档：https://typer.tiangolo.com/tutorial/package/ · 限制 https://github.com/fastapi/typer/issues/111

### 9. 打包与拉起（Claude Code hook 拉起 uvicorn）
关键发现（官方 hooks 文档）：
- SessionStart/SessionEnd/Setup **只支持 `type:"command"` 和 `type:"mcp_tool"`**，不支持 http/prompt/agent → 拉起 UI 必须 command hook。
- SessionEnd 默认超时 **1.5 秒**（可上调到 60s），关 server 要快（发 SIGTERM）。
- 插件 hook 写 `<plugin>/hooks/hooks.json`，启用插件时自动 merge。
- **exec form 优于 shell form**：`command`+`args` 数组，`${CLAUDE_PLUGIN_ROOT}` 原样传入无需引号转义。

拉起脚本 `scripts/start_ui.sh`：
```bash
#!/bin/bash
set -e
PORT_FILE="${CLAUDE_PLUGIN_DATA:-$HOME/.mlagent}/ui.port"
mkdir -p "$(dirname "$PORT_FILE")"
# 已在跑就复用
if [ -f "$PORT_FILE" ] && curl -s "http://127.0.0.1:$(cat "$PORT_FILE")/healthz" >/dev/null 2>&1; then exit 0; fi
PYTHON="${CLAUDE_PLUGIN_ROOT}/.venv/bin/python"
nohup "$PYTHON" -m mlagent.server --port 0 --port-file "$PORT_FILE" --project-root "${CLAUDE_PROJECT_DIR}" >/dev/null 2>&1 &
disown
for i in $(seq 1 50); do [ -f "$PORT_FILE" ] && break; sleep 0.1; done
if [ -f "$PORT_FILE" ]; then
  PORT=$(cat "$PORT_FILE")
  (command -v open >/dev/null && open "http://127.0.0.1:${PORT}") || (command -v xdg-open >/dev/null && xdg-open "http://127.0.0.1:${PORT}") || true
fi
exit 0
```
选空闲端口（server 内）：
```python
import socket
def find_free_port():
    with socket.socket() as s: s.bind(("",0)); return s.getsockname()[1]
```
hooks.json：
```json
{
  "hooks": {
    "SessionStart": [{ "matcher": "startup|resume", "hooks": [{ "type":"command", "command":"${CLAUDE_PLUGIN_ROOT}/scripts/start_ui.sh", "timeout":15 }] }],
    "SessionEnd": [{ "hooks": [{ "type":"command", "command":"${CLAUDE_PLUGIN_ROOT}/scripts/stop_ui.sh", "timeout":5 }] }]
  }
}
```
关键约束：SessionStart hook 必须**快**（`nohup & disown` 立即返回）；SessionEnd 1.5s 默认 → `pkill -f mlagent.server`；端口写文件让 hook 和 server 解耦。
已知坑：issue #11509 报告"本地 file-based marketplace 插件 SessionStart hook 不触发"——本地开发可先用 `.claude/settings.json` 直接注册 hook 绕过。
文档：https://code.claude.com/docs/en/hooks · https://code.claude.com/docs/en/plugins

### 10. 依赖管理（pyproject.toml + uv）
```toml
[project]
name = "mlagent"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.135.0",       # 内置 SSE
    "uvicorn[standard]>=0.30",# standard 含 watchfiles/httptools/websockets
    "pydantic>=2.7",
    "pyyaml>=6.0",
    "typer>=0.12",
    "rich>=13",
]
[project.optional-dependencies]
dev = ["pytest>=8", "httpx>=0.27"]
[project.scripts]
mlagent = "mlagent.cli:app"
```
`uvicorn[standard]` 已把 `watchfiles` 拉进来，文件监听零额外依赖。前端 JS 资产（Alpine/highlight.js/CM6 bundle）**不进 Python 依赖**，作为静态文件打进 `assets/` 或运行时从 CDN 取（更稳是预下载进 `assets/` 离线分发）。
文档：https://docs.astral.sh/uv/guides/projects/

## 三、一句话技术栈结论

**前端 Alpine.js（单文件 + import map，零 Node 构建）+ 后端 FastAPI（官方内置 `fastapi.sse.EventSourceResponse`）+ 推送 SSE（EventSource 原生重连）+ 监听 watchfiles `awatch`（随 `uvicorn[standard]` 隐式免费）+ 编辑写回 CodeMirror 6（esm.sh 免构建）+ CLI Typer（回调内桥接 Pydantic v2）+ SessionStart command hook exec form 拉起 uvicorn 子进程（`socket.bind(("",0))` 选空闲端口 + 端口文件 + webbrowser.open）+ pyproject.toml/uv**；Python 运行时净新增依赖约 5 个（fastapi/uvicorn[standard]/pydantic/pyyaml/typer，rich 随 typer），前端零构建、零 npm，完全契合「本地单用户、少依赖、Claude Code hook 可靠拉起」三条硬约束。

## Sources
- FastAPI SSE: https://fastapi.tiangolo.com/tutorial/server-sent-events/
- Claude Code Hooks: https://code.claude.com/docs/en/hooks · Plugins: https://code.claude.com/docs/en/plugins · Marketplace: https://code.claude.com/docs/en/plugin-marketplaces
- watchfiles: https://github.com/samuelcolvin/watchfiles · https://watchfiles.helpmanual.io/
- uv: https://docs.astral.sh/uv/guides/projects/
- Typer 打包: https://typer.tiangolo.com/tutorial/package/ · Typer+Pydantic 限制: https://github.com/fastapi/typer/issues/111
- CodeMirror 6: https://codemirror.net/ · https://github.com/RPGillespie6/codemirror-quickstart · Sourcegraph 迁移: https://sourcegraph.com/blog/migrating-monaco-codemirror
- highlight.js: https://github.com/highlightjs/highlight.js
- Alpine.js: https://github.com/alpinejs/alpine · petite-vue: https://github.com/vuejs/petite-vue
- 本地插件 SessionStart bug: https://github.com/anthropics/claude-code/issues/11509
