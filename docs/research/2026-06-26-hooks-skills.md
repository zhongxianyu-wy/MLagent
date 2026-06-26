# Hooks 与 Skill 组件参考调研

> Backref: [设计 spec](../superpowers/specs/2026-06-26-mlagent-redesign-spec.md) · Date: 2026-06-26 · 来源: GitHub（obra/superpowers、anthropics 官方）+ Claude Code 官方文档（已逐条核实）

## 一、候选/参考总览

| repo / 资源 | URL | 可借鉴点 | 对应 MLagent 组件 | 复用方式 |
|---|---|---|---|---|
| **obra/superpowers** | https://github.com/obra/superpowers | `hooks/hooks.json` 极简 + 无扩展名 `session-start` 脚本（读 SKILL.md → bash 参数替换 JSON 转义 → 包成 `additionalContext` 注入）；跨平台 `run-hook.cmd` polyglot | `SessionStart`（注入 `mlagent-bootstrap`）| **直接套用** session-start 模式（读 using-superpowers 换成读 mlagent-bootstrap） |
| superpowers `using-superpowers` SKILL.md | https://github.com/obra/superpowers/blob/main/skills/using-superpowers/SKILL.md | intent-style、`<EXTREMELY-IMPORTANT>` 框、"至少 1% 概率适用就调用"强 trigger、progressive disclosure | `mlagent-bootstrap` | 套用"会话第一句就激活 + 注入流程地图"范式 |
| superpowers `writing-skills` SKILL.md | https://github.com/obra/superpowers/blob/main/skills/writing-skills/SKILL.md | SDO（description 只写 when 不写 what）；frontmatter 模板；目录扁平化 | 全部 5 skill 写法规范 | 作 SKILL.md 自检清单 |
| superpowers `test-driven-development` SKILL.md | https://github.com/obra/superpowers/blob/main/skills/test-driven-development/SKILL.md | frontmatter 只两字段；断言式 `## Iron Law`；graphviz 流程图；When to Use/NOT 分节 | `instance-to-sop`、`retrain-from-sop` 骨架 | 套 When to Use/NOT 分节 |
| superpowers `tests/claude-code/` | https://github.com/obra/superpowers/tree/main/tests/claude-code | bash 驱动的 skill 行为测试（subagent 跑 baseline vs skill-on） | MLagent skill 测试 | 参考其 TDD-for-skills 法 |
| **anthropics/claude-plugins-official `example-plugin`** | https://github.com/anthropics/claude-plugins-official/tree/main/plugins/example-plugin | 标准插件目录：`.claude-plugin/plugin.json` + `.mcp.json` + `commands/` + `skills/` + `hooks/`（全套组件共存） | 整个插件骨架 | **直接套用**目录布局 |
| claude-plugins-official `skill-creator` | https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator | SKILL.md + scripts/ + references/ + assets/ + agents/ + eval-viewer/ 完整范本 | `instance-to-sop` | 参考"草稿→测试→跑→评估→改写"循环 |
| **Claude Code 官方 hooks 文档** | https://code.claude.com/docs/en/hooks | 全部事件/matcher/退出码/`additionalContext` 10k 上限/async/asyncRewake | 3 个 hook 契约 | 权威依据 |
| 官方 plugins 文档 | https://code.claude.com/docs/en/plugins-reference | plugin.json schema、组件发现规则、`bin/` 自动进 PATH | `bin/mlagent` | 权威依据 |

## 二、superpowers 深度（核心，逐字套用）

### 2.1 `.claude-plugin/plugin.json`（实测）
```json
{
  "name": "superpowers",
  "description": "Core skills library for Claude Code: TDD, debugging, collaboration patterns, and proven techniques",
  "version": "6.0.3",
  "author": { "name": "Jesse Vincent", "email": "jesse@fsck.com" },
  "homepage": "https://github.com/obra/superpowers",
  "repository": "https://github.com/obra/superpowers",
  "license": "MIT",
  "keywords": ["skills", "tdd", "debugging", "collaboration", "best-practices", "workflows"]
}
```
来源：https://raw.githubusercontent.com/obra/superpowers/main/.claude-plugin/plugin.json
**MLagent 改**：`name:"mlagent"` + version/description（description 仅标识用途，不含逻辑；trigger 写在各 SKILL.md frontmatter）。无 `entry_point/main`，Claude Code 靠约定目录发现组件。

### 2.2 `hooks/hooks.json`（实测，极简）
```json
{
  "hooks": {
    "SessionStart": [{
      "matcher": "startup|resume|clear|compact",
      "hooks": [{
        "type": "command",
        "command": "\"${CLAUDE_PLUGIN_ROOT}/hooks/run-hook.cmd\" session-start.sh"
      }]
    }]
  }
}
```
来源：https://raw.githubusercontent.com/obra/superpowers/main/hooks/hooks.json
关键点：
- `matcher` 用 `|` 列全部 4 个 SessionStart 来源，确保 `/clear`/resume/compact 后都重注入（UI 状态、manifest 都要刷新）。
- `${CLAUDE_PLUGIN_ROOT}` 是官方占位符，插件启用时替换为安装目录。
- **不是** `"async": true`。issue #444 实证 `async:true` 会让 `additionalContext` 被静默丢弃——MLagent 的 SessionStart **必须同步**。

**MLagent 改**：直接套用，再加 `PostToolUse`（matcher `Write|Edit|Bash`）和 `Stop`（无 matcher）。`PostToolUse` 退出码 2 不可阻塞（工具已执行），只能 `additionalContext` 提示；`Stop` 用 `decision:"block"`+reason 会继续会话。

### 2.3 `hooks/session-start`（实测，核心注入逻辑）
文件名**无扩展名**（不是 `session-start.sh`）—— run-hook.cmd 注释：Claude Code 在 Windows 上对含 `.sh` 的命令会自动 prepend bash，干扰跨平台调用。
```bash
#!/usr/bin/env bash
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLUGIN_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
using_superpowers_content=$(cat "${PLUGIN_ROOT}/skills/using-superpowers/SKILL.md" 2>&1 || echo "Error reading skill")

# bash 参数替换做 JSON 转义（比逐字符循环快几个数量级，无 jq 依赖）
escape_for_json() {
    local s="$1"
    s="${s//\\/\\\\}"; s="${s//\"/\\\"}"; s="${s//$'\n'/\\n}"; s="${s//$'\r'/\\r}"; s="${s//$'\t'/\\t}"
    printf '%s' "$s"
}
using_superpowers_escaped=$(escape_for_json "$using_superpowers_content")
session_context="<EXTREMELY_IMPORTANT>\nYou have superpowers.\n\n**Below is the full content of your 'superpowers:using-superpowers' skill ...**\n\n${using_superpowers_escaped}\n</EXTREMELY_IMPORTANT>"

if [ -n "${CURSOR_PLUGIN_ROOT:-}" ]; then
  printf '{\n  "additional_context": "%s"\n}\n' "$session_context" | cat
elif [ -n "${CLAUDE_PLUGIN_ROOT:-}" ] && [ -z "${COPILOT_CLI:-}" ]; then
  printf '{\n  "hookSpecificOutput": {\n    "hookEventName": "SessionStart",\n    "additionalContext": "%s"\n  }\n}\n' "$session_context" | cat
else
  printf '{\n  "additionalContext": "%s"\n}\n' "$session_context" | cat
fi
exit 0
```
来源：https://raw.githubusercontent.com/obra/superpowers/main/hooks/session-start

**逐字套用点**：
1. JSON 转义用 bash 参数替换（比逐字符循环快几个数量级，无 jq）。
2. stdout 直接是 JSON（SessionStart 事件下 exit 0 的 stdout 进 Claude 上下文）。
3. `additionalContext` 包在 `<EXTREMELY_IMPORTANT>` 里——让模型"必须读"的软约束。
4. **硬约束**：`additionalContext` 上限 **10,000 字符**；超出写文件给"预览+路径"。MLagent 的 `mlagent-bootstrap` SKILL.md 须控制在 ~3-4k 字符（留余地给 memory 状态摘要）。

**MLagent 改**：读 using-superpowers 换成读 `skills/mlagent-bootstrap/SKILL.md` + 追加"当前 memory 状态"（探查 raw_memory 条目数、SOP 库版本号、UI 是否已起）。**只输出 Claude Code 格式**（去掉 Cursor/Copilot 分支，YAGNI）。

### 2.4 `hooks/run-hook.cmd`（跨平台 polyglot）
文件头 `@echo off`（Windows cmd 段），heredoc `CMDBLOCK` 包裹，Unix 段末尾 `exec bash`。Windows 段按序找 Git Bash → 找不到静默 exit 0（保证插件在无 Git Bash 的 Windows 上也不报错）。
**MLagent 改**：若只 macOS/Linux，**可省略** run-hook.cmd，hooks.json 直接 `command:"${CLAUDE_PLUGIN_ROOT}/hooks/session-start"`（官方推荐 exec form：`command`+`args` 数组）。要兼容 Windows 照搬。

### 2.5 skill 目录与 SKILL.md 范式
superpowers 共 14 skill。共性：
- **扁平结构**：`skills/<name>/SKILL.md` + 可选 `references/`、`scripts/`、`examples/`。无嵌套命名空间。
- **frontmatter 极简**：
  ```yaml
  ---
  name: writing-skills
  description: Use when creating new skills, editing existing skills, or verifying skills work before deployment
  ---
  ```
  只 name + description。description **严格以 "Use when ..." 开头**，只写触发条件，绝不写 workflow（SDO：描述里写 workflow 会让 agent 走捷径跳过正文）。
- **intent-style 正文**：`## Overview` → `## When to Use`（含 SYMPTOMS）→ `## Core Pattern` → `## Common Mistakes`。命令式短句、graphviz 流程图、`<EXTREMELY-IMPORTANT>` 框。
- **progressive disclosure**：重型参考拆 `references/`，正文只留判断和决策。
- **测试驱动写 skill**：`tests/claude-code/` bash 脚本用 subagent 跑 baseline vs skill-on。

## 三、官方规范要点（核实后最新事实）

文档：https://code.claude.com/docs/en/hooks + https://code.claude.com/docs/en/plugins-reference

### 3.1 事件
- **SessionStart**：matcher=`startup|resume|clear|compact`；**仅支持 `command`/`mcp_tool` 类型**（不支持 http/prompt/agent）。输入含 `source`/`model`/`session_title`。输出可 `additionalContext`/`sessionTitle`/`watchPaths`/`reloadSkills`（装新 skill 后本 session 立即可用）。
- **PostToolUse**：matcher 按工具名（`Write|Edit|Bash`）。输入含 `tool_input`（带 `file_path`/`command`）+ `tool_response` + `duration_ms`。退出码 2 **不可阻塞**（工具已执行完），只能 `additionalContext`/`updatedToolOutput`（可改写工具输出再喂模型）。
- **PostToolBatch**：一批并行工具全部完成后触发一次（PostToolUse 是每个一次）。输入 `tool_calls` 数组。适合"这批改动整体后处理"。
- **Stop**：无 matcher，每次触发。输入含 `stop_hook_active`（防无限循环，连续 8 次 block 后强制停）、`last_assistant_message`、`background_tasks`、`session_crons`。`decision:"block"`+reason → 继续；`additionalContext` → 非错误反馈。
- **PreCompact/PostCompact**：matcher=`manual|auto`。PostCompact 输入含 `compact_summary`——可在此刷新 memory 索引。
- **SessionEnd**：默认超时 **1.5 秒**（`/clear`/`/resume`/退出都算）。要更长设 per-hook `timeout` 或环境变量 `CLAUDE_CODE_SESSIONEND_HOOKS_TIMEOUT_MS`。**关 UI 必须快或显式设 timeout。**

### 3.2 hook 类型（5 种）
`command`/`http`/`mcp_tool`/`prompt`/`agent`。SessionStart 只支持 command/mcp_tool。`prompt` hook 把输入+你的 prompt 喂快模型返回 `{ok,reason}`；`agent` hook 派子 agent 可用 Read/Grep（最多 50 轮）——**Stop hook 触发"经验蒸馏"重 LLM 任务，正解是 `agent` 类型 hook 或 async command hook**。

### 3.3 配置位置
插件内：`hooks/hooks.json`（顶层可加 `description`）。skill/agent frontmatter 也可声明 hook（`once:true` 仅 frontmatter 生效，会话跑一次后移除）。`${CLAUDE_PROJECT_DIR}`/`${CLAUDE_PLUGIN_ROOT}`/`${CLAUDE_PLUGIN_DATA}` 三个占位符。exec form（command+args 数组）优先。

### 3.4 退出码语义
- `exit 0`：成功，解析 stdout JSON。
- `exit 2`：阻塞错误，stderr 喂 Claude。**PostToolUse 不可阻塞**（只显示 stderr）。
- 其他：非阻塞错误，显示 `<hook> hook error` + stderr 首行。

### 3.5 `additionalContext` 上限
**硬上限 10,000 字符**。超出 → 写进 session 目录文件，给"预览 + 文件路径"。多个 hook 返回的会拼接。

### 3.6 async hook / asyncRewake
`async:true`（仅 command 类型）→ 后台跑不阻塞，完成后 `additionalContext` 在**下一轮**对话送达。`asyncRewake:true` → 后台跑，exit 2 立即唤醒 Claude 并把 stderr 当 system reminder。

### 3.7 plugin.json
`name`（唯一必填）/`version`/`description`/`author`/`homepage`/`repository`/`license`/`keywords`。**无逻辑字段**——组件靠约定目录发现。`example-plugin` 实测就是全集。

### 3.8 skill 命名空间
插件内调用形如 `/plugin:skill`（如 `superpowers:using-superpowers`）。frontmatter `name` 必须 kebab-case，与目录名一致，≤64 字符。

## 四、5 个 skill 的 SKILL.md 写法建议

### 4.1 `mlagent-bootstrap`（主 skill，SessionStart 注入）
```yaml
---
name: mlagent-bootstrap
description: Use when starting or resuming any ML R&D session — establishes the MLagent workflow (explore→train→distill→SOP→retrain), how to record raw_memory, how to maintain the manifest, and the current SOP library status. Loaded automatically at session start.
---
```
结构（intent-style，< 3.5k 字符留余地给 memory 状态）：`<EXTREMELY-IMPORTANT>` 框（本会话由 MLagent 接管）→ Workflow map（5 skill 何时触发）→ How to record raw_memory（只记摘要+路径+时间戳）→ Manifest 维护（每次脚本改动更新 manifest）→ SOP 库状态（版本号/最近 distill 时间）→ Gotchas（UI 已开别重复拉起；/clear 后状态重建）。
**特殊**：全文由 SessionStart hook 注入（非等模型主动调用），description 是路由占位，强约束靠 `<EXTREMELY-IMPORTANT>` 框。

### 4.2 `explore-train`（探索+训练编排）
```yaml
---
name: explore-train
description: Use when the user wants to explore a dataset, build a baseline model, or run a training experiment — before writing training scripts. Produces structured scripts + manifest entry + log + metrics.
---
```
结构：`## When to Use`（SYMPTOMS：跑 baseline、调参、对比实验）/ `## When NOT`（纯推理部署、数据清洗单独走）/ `## Procedure`（探索→脚本骨架→manifest→tee 日志→指标落盘）/ `## Outputs`（脚本路径、metrics schema）/ `## Gotchas`（忘记 tee、manifest 漏更）。重型参考（脚本模板、metrics schema）放 `references/`。

### 4.3 `distill-experience`（分阶段自动蒸馏）
```yaml
---
name: distill-experience
description: Use after accumulating raw_memory entries (triggered by Stop hook or explicit request) to distill meaningful experience into the experience layer — staged by exploration count (e.g. every 5/10/20 runs).
---
```
结构：`## Stages`（N<5 不蒸馏 / 5-10 浅蒸馏 / 10+ 深蒸馏）/ `## Procedure`（读 raw_memory → LLM 聚类提经验 → 写 experience 层）/ `## What to distill vs discard`（经验≠流水账）。**由 Stop hook 异步触发**（见第六节）。

### 4.4 `instance-to-sop`（实例→候选 SOP）
```yaml
---
name: instance-to-sop
description: Use when a training instance or experiment has been verified to work and should be promoted into a reusable SOP — runs the instance, verifies the test passes, then drafts a candidate SOP version.
---
```
结构：`## Procedure`（跑通实例→确认测试绿→提取步骤→生成 `sops/vX.Y-candidate/SOP.md`+`test/`）/ `## Outputs`（候选 SOP 版本目录）/ `## Gotchas`（测试不绿别晋升、版本号冲突）。参考 skill-creator 的"草稿→测试→评估→改写"循环。

### 4.5 `retrain-from-sop`（按版本重训）
```yaml
---
name: retrain-from-sop
description: Use when the user wants to retrain or reproduce a run from a specific SOP version — locates the SOP, applies its steps, and compares results against the recorded baseline.
---
```
结构：`## Procedure`（解析版本号→读 SOP→按步骤重训→对比 metrics）/ `## Outputs`（对比报告）/ `## Gotchas`（环境漂移、数据版本不匹配）。

**通用规范**：description 只写 "Use when ..."；`## When NOT to use` 必须有；命令式短句 + graphviz 流程图；重型参考拆 `references/`；`allowed-tools` 最小权限。

## 五、PostToolUse 捕获范式（写 raw_memory 草稿）

从 hook 输入拿字段（jq）：
```bash
#!/usr/bin/env bash
INPUT=$(cat)
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // empty')
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // empty')
TOOL=$(echo "$INPUT" | jq -r '.tool_name // empty')

# 训练命令 → 提示 tee 日志（PostToolUse 不可阻塞，只能 additionalContext）
if echo "$CMD" | grep -qE 'python.*train|torchrun|accelerate'; then
  jq -nc --arg c "$CMD" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:("Training command detected — ensure output is tee-d to .mlagent/runs/<ts>.log. cmd: " + $c)}}'
  exit 0
fi
# Write/Edit 脚本 → 写 raw_memory 草稿 + 提示更新 manifest
case "$TOOL" in
  Write|Edit) case "$FILE_PATH" in
    *.py|*.ipynb)
      TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)
      printf '%s\t%s\t%s\n' "$TS" "script_change" "$FILE_PATH" >> "${CLAUDE_PROJECT_DIR}/.mlagent/raw_memory/drafts.tsv"
      jq -nc --arg f "$FILE_PATH" '{hookSpecificOutput:{hookEventName:"PostToolUse",additionalContext:("Script modified: " + $f + " — remember to update manifest.json if entrypoint/inputs changed.")}}'
      ;;
  esac ;;
esac
exit 0
```
关键：PostToolUse `exit 2` 不可阻塞，只能 `additionalContext` 提示；单条上限 10k，多条会拼接。

## 六、Stop hook 触发异步"经验蒸馏"的正确姿势

**方案 A（推荐）：`async:true` command hook**
```json
{ "hooks": { "Stop": [{ "hooks": [{ "type":"command", "command":"${CLAUDE_PLUGIN_ROOT}/hooks/on-stop.sh", "async":true, "timeout":300 }] }] } }
```
Stop 触发立即放行（不阻塞用户结束）；`on-stop.sh` 后台跑，结束后 `additionalContext` 在**下一轮对话**送达。async hook 的 `decision`/`continue` 无效（动作已完成）。蒸馏是后台批处理，结果下次自然注入——最适合。

方案 B `asyncRewake:true`：exit 2 立即唤醒。但设计给"后台失败需立即处理"，不适合蒸馏。
方案 C `type:"agent"` hook：派子 agent 可 Read/Grep（最多 50 轮）。但**同步阻塞**（默认 timeout 60s），延迟会话结束。仅蒸馏必须本会话内完成才用。

stderr ready-marker：官方未定义通用 ready-marker 协议；MLagent 的 UI 进程管理（拉起/关闭）应在 hook 脚本里直接 `nohup`/`kill`，不依赖 ready-marker。

**推荐**：方案 A，`on-stop.sh` 后台做"会话总结 + 触发 distill（达阈值才跑）+ 关 UI"。蒸馏本身重，用独立脚本而非 prompt/agent hook。

## 七、复用结论

### 7.1 最该 fork / 参考
**首推 fork obra/superpowers 的 hook 基建**（hooks/hooks.json + session-start + run-hook.cmd）。MIT，已上官方 marketplace，跨平台 polyglot wrapper 和 bash 参数替换 JSON 转义是踩过 Windows/路径/转义无数坑后的沉淀，直接套用省掉 90% 调试。
SKILL.md 写法参考 superpowers 的 writing-skills + using-superpowers（SDO、`<EXTREMELY-IMPORTANT>` 框、intent-style、progressive disclosure）。官方 skill-creator 的"草稿→测试→评估→改写"循环可作 instance-to-sop 内循环范本。

### 7.2 直接套用（无需改）
- 插件目录结构（套 example-plugin）。
- plugin.json schema（套 superpowers）。
- SessionStart "读 SKILL.md → 转义 → additionalContext" 流程。
- PostToolUse 的 jq 取字段 + additionalContext 反馈。
- Stop 的 async command 模式。

### 7.3 自研
- memory 三层结构（raw/experience/skill-SOP）：无现成 Claude Code 插件实现，需自研 schema。
- bin/mlagent CLI 命令（拉 UI、查 memory、触发 distill）。
- PostToolUse 的"训练命令 tee 日志"启发式（grep `python.*train|torchrun`）。
- 5 个 skill 的 ML 业务逻辑（探索编排、分阶段蒸馏阈值、SOP 晋升、版本化重训对比）。

### 7.4 关键风险（来自 superpowers issues）
1. **SessionStart 别用 `async:true`**（issue #444：additionalContext 被静默丢弃）。
2. **hook 脚本用无扩展名**（避免 Windows 自动 prepend bash）。
3. **additionalContext 10k 上限**：bootstrap + memory 状态严控字数。
4. **PostToolUse 不可阻塞**：只能提示。
5. **SessionEnd 默认 1.5s**：关 UI 要么极快要么显式设 timeout。

## Sources
- obra/superpowers: https://github.com/obra/superpowers
- superpowers hooks.json: https://raw.githubusercontent.com/obra/superpowers/main/hooks/hooks.json
- superpowers session-start: https://raw.githubusercontent.com/obra/superpowers/main/hooks/session-start
- superpowers run-hook.cmd: https://raw.githubusercontent.com/obra/superpowers/main/hooks/run-hook.cmd
- superpowers plugin.json: https://raw.githubusercontent.com/obra/superpowers/main/.claude-plugin/plugin.json
- using-superpowers SKILL.md: https://github.com/obra/superpowers/blob/main/skills/using-superpowers/SKILL.md
- writing-skills SKILL.md: https://github.com/obra/superpowers/blob/main/skills/writing-skills/SKILL.md
- test-driven-development SKILL.md: https://github.com/obra/superpowers/blob/main/skills/test-driven-development/SKILL.md
- superpowers tests/claude-code/: https://github.com/obra/superpowers/tree/main/tests/claude-code
- issue #444 (async drops additionalContext): https://github.com/obra/superpowers/issues/444
- Hooks reference: https://code.claude.com/docs/en/hooks
- Hooks guide: https://code.claude.com/docs/en/hooks-guide
- Plugins reference: https://code.claude.com/docs/en/plugins-reference
- Plugins: https://code.claude.com/docs/en/plugins
- Plugin marketplaces: https://code.claude.com/docs/en/plugin-marketplaces
- example-plugin: https://github.com/anthropics/claude-plugins-official/tree/main/plugins/example-plugin
- skill-creator: https://github.com/anthropics/claude-plugins-official/tree/main/plugins/skill-creator
- anthropics/claude-code plugins/: https://github.com/anthropics/claude-code/tree/main/plugins
