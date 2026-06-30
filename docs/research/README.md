# MLagent v0.3 调研索引

> 调研日期: 2026-06-26 · 调研策略: 4 路并行（技术栈 + hooks/skill 参考 + 记忆系统参考 + UI 交互参考）· 来源: GitHub + 官方文档
>
> 设计依据: [重设计 spec](../superpowers/specs/2026-06-26-mlagent-redesign-spec.md)

## 调研文档

| 方向 | 文档 | 核心结论 |
|---|---|---|
| **实现技术栈** | [tech-stack](./2026-06-26-tech-stack.md) | FastAPI(内置 SSE) + Alpine.js/HTMX(零 Node 构建) + watchfiles(随 uvicorn[standard] 免费) + CodeMirror 6 + Typer(桥接 Pydantic) + uv；约 5 个 Python 依赖 |
| **hooks & skill 参考** | [hooks-skills](./2026-06-26-hooks-skills.md) | fork obra/superpowers 的 hook 基建（session-start 注入范式）；官方规范核实（SessionStart 仅 command/mcp_tool、additionalContext 10k 上限、SessionEnd 1.5s）；5 skill 写法骨架 |
| **记忆系统参考** | [memory-system](./2026-06-26-memory-system.md) | raw 借 A-MEM+Letta MemFS；experience 照搬 langmem Episode 四字段 + Letta dream 触发器；skill_library 借 MLEM+Graphiti bi-temporal。附三层 YAML schema 草案 |
| **UI 交互参考** | [ui-panels](./2026-06-26-ui-panels.md) | 面板 A 借 marimo reactive + Quarto annotation；面板 B 借 logdy + Virtuoso；面板 C 借 MLflow/Aim 表格设计；骨架用 FastAPI+HTMX+Shoelace 无构建 |

## 2026-06-30 深度调研（在 06-26 之上深化 + 拓宽，仅借鉴设计模式）

| 方向 | 文档 | 核心新发现（超越 06-26） |
|---|---|---|
| **记忆系统** | [memory-deepdive](./2026-06-30-research-memory-deepdive.md) | **新项目**：cass_memory_system（三层+**确定性 Curator 无 LLM**+成熟度 FSM candidate→established→proven→deprecated+反馈衰减）、icarus（**EvidencePointer `{kind,ref,excerpt,hash}`** + verified 生命周期 + 非破坏性回滚）、agentops（**棘轮门禁**：不自评/换 agent/失败即关/绑 commit，给 SOP 复现测试）、memoir（confidence 阈值 high/med/low）、Ori（**分区衰减倍率**：SOP 慢衰/低置信快衰）。落法：distill 两段式（LLM Reflector + 确定性 Curator）、experience 加 maturity/verified/derived_from、SOP 加 gate 块（fresh-verifier） |
| **UI 交互** | [ui-deepdive](./2026-06-30-research-ui-deepdive.md) | **新项目**：**trackio**（HF，"为人类和 agent 构建"的本地仪表盘标杆，forkable、轮询非 SSE、SQLite、frontend 只需 index.html）、SwanBoard（FastAPI+独立 Vue 双子，pip 内打包前端）、Phoenix（`Static(StaticFiles)` index.html-404 回退，构建产物入包的范式）、sklearn-evaluation（`SQLiteTracker.query(as_frame=True)→to_html()` 零图表依赖性能表）、logdy/FEMessage（日志 ring buffer+ANSI）、mandala（ComputationFrame=面板A 心智模型）。落法：SSE 推日志/manifest、Alpine 无构建 MVP（构建则 trackio build-at-wheel-time）、Phoenix 静态服务类 + trackio 最小 starter 兜底 |
| **Claude Code 插件** | [claude-code-plugins-deepdive](./2026-06-30-research-claude-code-plugins-deepdive.md) | **新项目**：**claude-smart**（插件内 UI sidecar 的标杆：SessionStart detached 拉起 FastAPI+Next.js、SessionEnd opt-in 拆除、marker-header 端口核验）、**Oh-my-paper**（最近工作流类比：experiment-driver agent + 分阶段 memory + TTL 缓存注入）。**新机制**：`Setup` hook（一次性构建 UI/venv）、`reloadSkills`+`watchPaths`（**动态 skill 桥**：approve-sop 写 `.claude/skills/<sop>-vXXX` + reloadSkills 让新 SOP 即时可调用）。**关键修正**：spec "Stop→ui stop" 应改为 "SessionEnd→ui stop（默认长驻）/Stop→仅 distill"；marketplace 相对 source 仅 repo-add 可用（URL fetch 会坏） |

> 三份深度报告均在 06-26 初步调研之上**只拓宽+深化**（优先 2025-2026 新项目），**仅借鉴模式**（file-first YAML/MD + 可选 SQLite，零运行时），每条建议标注灵感来源。

## 一句话总览

> **后端 FastAPI（官方内置 SSE）+ 文件监听 watchfiles + 前端 Alpine.js/HTMX（零 Node 构建，CodeMirror 6 编辑写回）+ CLI Typer+Pydantic；插件骨架 fork obra/superpowers（SessionStart command hook 拉起 uvicorn，端口文件解耦）；三层记忆借鉴 langmem(A-MEM)+Graphiti+MLEM 落盘 YAML；UI 三面板用 SSE 推 + 局部重渲染。约 5 个 Python 运行时依赖，前端零 npm，本地单用户、hook 可靠拉起。**

## 关键技术决策（来自调研）

- **推送**：SSE（非 WebSocket）—— 单向、浏览器原生重连、FastAPI 0.135+ 内置。
- **文件监听**：watchfiles `awatch`（随 `uvicorn[standard]` 隐式免费，Rust 后端）。
- **前端**：无 Node 构建（Alpine.js / HTMX + Shoelace CDN）—— 契合插件分发轻量。
- **脚本结构**：manifest 驱动（Claude 维护 `<script>.manifest.yaml`，UI 读 manifest+代码渲染）。
- **编辑写回**：CodeMirror 6 + `PUT /api/file`（防路径穿越 + 打 human_interventions）。
- **UI 拉起**：SessionStart command hook（exec form）→ `nohup uvicorn` 子进程 → `socket.bind(("",0))` 选空闲端口 → 端口文件 + 自动开浏览器；SessionEnd 快速 SIGTERM（默认 1.5s 超时）。
- **SessionStart hook 必须同步**（`async:true` 会丢 additionalContext，superpowers issue #444）。
- **experience 蒸馏**：Episode 四字段（observation/thoughts/action/result）+ 按探索次数阈值触发 + mem0 ADD/UPDATE/SUPERSEDE 去重。
- **skill_library 门禁**：`gate.tests_passed` 显式字段 + modelstore state 机 + Graphiti bi-temporal（valid_from/to + superseded_by，不删只追加）。

## 关联

- 设计 spec: [../superpowers/specs/2026-06-26-mlagent-redesign-spec.md](../superpowers/specs/2026-06-26-mlagent-redesign-spec.md)
