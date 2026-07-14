# PRD-Writer · 标准产品需求文档生成 Skill

> 一个 Claude Code Skill，把"想法 + 调研 + 头脑风暴结论"转化为符合行业标准的 14 章 PRD 文档。

---

## ✨ 核心特性

- 🇨🇳 **中文优先**，章节命名保留中英对照
- 📐 **14 章完整结构**，覆盖背景、用户、功能、验收、度量、风险全维度
- 🔗 **Vibe Coding 工作流深度对接**：Brainstorming → PRD → TRD
- 🤖 **AI Agent 友好**：Spec-Driven Development 范式，PRD 可被 AI 直接消费
- 📊 **场景化完整示例**：内置量化交易项目 PRD 全版
- ⚖️ **What/How 边界明确**：清晰的 PRD vs TRD 判定指南
- ✅ **反模式自检清单**：24 条 + 速查表，写完即查
- 🧩 **三种使用强度**：完整版（14 章）/ 精简版（9 章）/ 极简版（5 章）

---

## 📦 安装

### 方式 1：Claude Code 项目本地 Skill

```bash
# 把整个 prd-writer/ 目录复制到项目的 .claude/skills/ 下
cp -r prd-writer /path/to/your/project/.claude/skills/

# Claude Code 会自动发现并加载
```

### 方式 2：Claude Code 全局 Skill

```bash
# 复制到全局 Skills 目录
cp -r prd-writer ~/.claude/skills/

# 重启 Claude Code 生效
```

---

## 🚀 使用方式

### 触发方式（任一即可）

向 Claude Code 说：
- "帮我写一份 PRD"
- "把我的想法变成产品需求文档"
- "整理这些调研成产品规约"
- "用 prd-writer Skill 生成 PRD"
- 「请基于 brainstorming-design.md 写一份 PRD」

Claude Code 会自动识别并调用本 Skill。

---

## 📁 Skill 目录结构

```
prd-writer/
├── SKILL.md                                  # 主入口（必读）
├── README.md                                 # 本文件
├── evals/                                    # 评估用例（预留）
└── references/
    ├── 14-chapters-detailed.md               # 14 章详细模板与填充指南
    ├── prd-vs-trd-boundary.md                # What/How 边界判定
    ├── quant-trading-example.md              # 完整量化交易 PRD 示例
    ├── prd-anti-patterns.md                  # 反模式清单（24 条）
    └── workflow-integration.md               # Vibe Coding 9 步流程集成
```

---

## 📐 14 章 PRD 标准结构

| # | 章节 | 必/推/可 |
|:-:|------|:-:|
| 1 | 文档信息 | ★ |
| 2 | 项目背景与目标 | ★ |
| 3 | 目标用户与画像 | ★ |
| 4 | 用户故事 | ★ |
| 5 | 功能列表与范围 | ★ |
| 6 | 详细功能描述 | ★ |
| 7 | 非功能需求 | ★ |
| 8 | UI / 交互说明 | ☆ |
| 9 | 验收标准 | ★ |
| 10 | 优先级 / MVP 范围 | ★ |
| 11 | 度量指标 | ★ |
| 12 | 依赖与约束 | ☆ |
| 13 | 风险与开放问题 | ★ |
| 14 | 里程碑 / 时间计划 | ☆ |

---

**版本**：v1.0
**最后更新**：2026-05-19
