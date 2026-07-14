# Position Paper: MLflow (AI 工程平台)

> **Owned Project**: MLflow (https://github.com/mlflow/mlflow)
> **License**: Apache-2.0 | **Stars**: 26,039 | **Python**: 3.10+
> **Stance**: MLflow 是 MLagent_v2 实验追踪层的行业标准选择——26K Stars 验证的完整 AI 工程平台，实验追踪 + 模型注册 + Prompt 注册 + OpenTelemetry 追踪四位一体，与 mem0 语义记忆形成完美互补。

---

## 1. 架构总览

### 1.1 Mermaid 架构图

```mermaid
graph TD
    subgraph Input["输入层"]
        A["Python 训练脚本\nsklearn / XGBoost / PyTorch"]
        B["Agent 探索循环\nAIDE / 自研引擎"]
        C["Prompt 模板\nSKILL.md 动态加载"]
    end

    subgraph Core["MLflow 核心引擎"]
        D["Fluent API\nmlflow.start_run() / log_metric()"]
        E["MlflowClient\n统一 CRUD 接口"]
        F["TrackingServiceClient\n实验追踪服务"]
        G["ModelRegistryClient\n模型注册服务"]
        H["TracingClient\nOpenTelemetry 追踪"]
    end

    subgraph Entities["核心实体"]
        I["Experiment\n实验（参数/指标集合）"]
        J["Run\n单次运行（RunInfo + RunData + RunInputs）"]
        K["Metric\n时间序列指标"]
        L["Param\n静态参数"]
        M["RegisteredModel\n注册模型"]
        N["PromptVersion\nPrompt 版本"]
        O["Trace\nLLM 调用链路"]
    end

    subgraph Storage["存储层"]
        P["FileStore\n本地文件系统（默认）"]
        Q["SQLStore\nSQLite / PostgreSQL / MySQL"]
        R["Artifact Store\n本地目录 / S3 / GCS / Azure"]
    end

    subgraph Output["输出层"]
        S["MLflow UI\nlocalhost:5000"]
        T["实验对比视图"]
        U["模型版本管理"]
        V["Prompt 注册表"]
    end

    A -->|autolog| D
    B -->|手动 log| D
    C -->|register_prompt| E
    D --> E
    E --> F & G & H
    F --> I & J & K & L
    G --> M
    H --> O
    F & G & H --> P & Q & R
    P & Q & R --> S & T & U & V
```

### 1.2 主目录结构

```
mlflow/
├── mlflow/
│   ├── __init__.py              # 顶层 Fluent API 导出
│   ├── tracking/
│   │   ├── fluent.py            # Fluent API: start_run, log_metric, log_param (~3313 行)
│   │   ├── client.py            # MlflowClient: 统一 CRUD (~5505 行)
│   │   ├── _tracking_service/
│   │   │   └── client.py        # TrackingServiceClient
│   │   ├── _model_registry/
│   │   │   └── client.py        # ModelRegistryClient
│   │   └── _workspace/
│   │       └── client.py        # WorkspaceProviderClient
│   ├── entities/
│   │   ├── run.py               # Run = RunInfo + RunData + RunInputs + RunOutputs
│   │   ├── run_info.py          # RunInfo: run_id, experiment_id, status, artifact_uri
│   │   ├── experiment.py        # Experiment: experiment_id, name, artifact_location
│   │   ├── metric.py            # Metric: key, value, timestamp, step
│   │   └── model_registry/      # RegisteredModel, ModelVersion, Prompt, PromptVersion
│   ├── tracing/
│   │   ├── client.py            # TracingClient
│   │   ├── fluent.py            # start_span, end_span
│   │   └── provider.py          # OpenTelemetry 导出器配置
│   ├── store/
│   │   ├── tracking/            # FileStore, SQLStore
│   │   └── artifact/            # 本地/S3/GCS/Azure 工件存储
│   └── utils/
│       └── autologging_utils.py # 60+ 框架自动日志
├── mlflow/server/               # REST API 服务器
├── mlflow/ui/                   # React 前端
└── pyproject.toml
```

---

## 2. 核心能力清单

### 2.1 双层 API 设计（Fluent + Client）

MLflow 提供两种 API 风格，覆盖从脚本到生产系统的全场景：

**Fluent API**（`mlflow.tracking.fluent`）——适合训练脚本内嵌：

**源码证据**（`mlflow/tracking/fluent.py:116`）：
```python
_active_run_stack = ThreadLocalVariable(default_factory=lambda: [])
_last_active_run_id = ThreadLocalVariable(default_factory=lambda: None)

def set_experiment(experiment_name: str | None = None, experiment_id: str | None = None):
    """设置当前活动实验，自动创建不存在的实验"""

def start_run(run_id=None, experiment_id=None, run_name=None, nested=False):
    """启动新 Run，支持嵌套 Run（超参数搜索场景）"""

def log_metric(key: str, value: float, step=None):
    """记录时间序列指标"""

def log_param(key: str, value: Any):
    """记录静态参数"""

def log_artifact(local_path: str, artifact_path: str | None = None):
    """记录工件文件（模型、图表、配置）"""
```

**Client API**（`mlflow.tracking.client.MlflowClient`）——适合程序化管理和查询：

**源码证据**（`mlflow/tracking/client.py:193-228`）：
```python
class MlflowClient:
    """
    Client of an MLflow Tracking Server that creates and manages experiments and runs,
    and of an MLflow Registry Server that creates and manages registered models and
    model versions. It's a thin wrapper around:
    - TrackingServiceClient for tracking operations
    - WorkspaceProviderClient for workspace operations
    - ModelRegistryClient for registry operations
    """
    def __init__(self, tracking_uri=None, registry_uri=None, workspace_store_uri=None):
        final_tracking_uri = utils._resolve_tracking_uri(tracking_uri)
        self._tracking_client = TrackingServiceClient(final_tracking_uri)
        self._tracing_client = TracingClient(final_tracking_uri)
        self._workspace_client = None  # 懒加载
        # ModelRegistryClient 懒加载于 _get_registry_client()
```

**对 MLagent_v2 的价值**：
- 探索引擎（AIDE）用 Fluent API 在训练脚本中记录指标
- Agent 管理层用 Client API 查询历史实验、对比结果
- 嵌套 Run 支持超参数搜索（外层 Run = 实验，内层 Run = 每组超参数）

### 2.2 60+ 框架自动日志（autolog）

MLflow 的 `autolog()` 自动拦截主流 ML 框架的调用，无需手动 `log_metric`：

```python
import mlflow
mlflow.sklearn.autolog()    # 自动记录：模型类型、参数、指标、模型文件
mlflow.xgboost.autolog()    # 自动记录：n_estimators、max_depth、AUC、feature_importance

with mlflow.start_run():
    model.fit(X_train, y_train)  # 零代码记录全部实验信息
```

**对 MLagent_v2 的价值**：Agent 生成的训练脚本只需在开头加两行 `autolog()` 调用，所有参数和指标自动进入 MLflow，无需修改脚本逻辑。

### 2.3 模型注册与版本管理

`ModelRegistryClient` 提供生产级的模型生命周期管理：

**源码证据**（`mlflow/tracking/client.py` 模型注册方法）：
```python
def create_registered_model(self, name: str, description=None, tags=None):
    """注册新模型"""

def create_model_version(self, name: str, source: str, run_id=None):
    """创建模型新版本"""

def transition_model_version_stage(self, name, version, stage):
    """切换模型阶段：Staging / Production / Archived"""

def set_registered_model_alias(self, name: str, alias: str, version: str):
    """设置模型别名（如 "production" → version 3）"""
```

**对 MLagent_v2 的价值**：
- 探索成功的模型可注册为 `"ngs-methylation-xgboost"`
- 通过别名 `"production"` 指向当前最优版本
- Skill 可引用 `"models:/ngs-methylation-xgboost/production"` 加载模型

### 2.4 Prompt 注册表（Prompt Registry）

MLflow 3.x 引入的 Prompt 注册表是管理 LLM Prompt 版本的基础设施：

**源码证据**（`mlflow/tracking/client.py:580-712`）：
```python
def register_prompt(self, name: str, template: str, commit_message=None, tags=None,
                    response_format=None, model_config=None):
    """
    注册 Prompt 模板到 MLflow Prompt Registry。
    支持 {{variable}} 变量插值和聊天消息列表格式。
    """

def load_prompt(self, name_or_uri: str, version=None, allow_missing=False):
    """
    加载指定版本的 Prompt。支持缓存（默认 TTL 60s）。
    URI 格式：prompts:/name/version 或 prompts:/name@alias
    """

def search_prompts(self, filter_string=None, max_results=1000):
    """搜索 Prompt，支持 filter 表达式"""
```

**对 MLagent_v2 的价值**：
- NGS 领域 Prompt 模板可版本化管理（如 `"ngs-feature-generation-prompt" v1, v2, v3`）
- Skill 中的 Prompt 可从 MLflow 动态加载，实现 Prompt A/B 测试
- 实验与 Prompt 版本关联：知道"实验 #42 使用的是 Prompt v2"

### 2.5 OpenTelemetry 追踪（Tracing）

MLflow 的 `TracingClient` 基于 OpenTelemetry 标准，记录 LLM 调用链路：

**源码证据**（`mlflow/tracking/client.py:1110-1176`）：
```python
def get_trace(self, trace_id: str, display=True, flush=False) -> Trace:
    """获取指定 trace_id 的完整追踪数据"""

def delete_traces(self, experiment_id, max_timestamp_millis=None,
                  max_traces=None, trace_ids=None) -> int:
    """删除追踪数据，返回删除数量"""

def link_traces_to_run(self, trace_ids: list[str], run_id: str) -> None:
    """将多个 trace 关联到指定 run"""
```

**对 MLagent_v2 的价值**：
- 记录每次 LLM 调用的输入/输出/token 消耗
- 追踪 Agent 的决策链路（"为什么选择了这组特征？"）
- 与 MLflow Run 关联：完整复现实验的 LLM 交互历史

### 2.6 零配置本地部署

```bash
mlflow ui --port 5000
```

默认使用本地文件存储（`./mlruns`），无需数据库服务器。生产环境可切换为 PostgreSQL + S3：

```bash
export MLFLOW_TRACKING_URI=postgresql://user:pass@localhost/mlflow
export MLFLOW_ARTIFACT_ROOT=s3://my-bucket/mlflow-artifacts
```

---

## 3. 数据模型

### 3.1 Experiment（实验）

**源码证据**（`mlflow/entities/experiment.py`）：
```python
class Experiment:
    experiment_id: str          # 唯一 ID
    name: str                   # 实验名称（如 "NGS-Methylation-Classification"）
    artifact_location: str      # 工件存储位置
    lifecycle_stage: str        # active / deleted
    tags: Dict[str, str]        # 自定义标签
    creation_time: int          # 创建时间戳（毫秒）
    last_update_time: int       # 最后更新时间戳
```

### 3.2 Run（运行）

**源码证据**（`mlflow/entities/run.py`）：
```python
class Run:
    info: RunInfo       # 运行元数据
    data: RunData       # 参数 + 指标 + 标签
    inputs: RunInputs   # 输入数据集
    outputs: RunOutputs # 输出模型/工件

class RunInfo:
    run_id: str
    experiment_id: str
    user_id: str
    status: str         # RUNNING / SCHEDULED / FINISHED / FAILED / KILLED
    start_time: int
    end_time: int
    lifecycle_stage: str
    artifact_uri: str
    run_name: str
```

### 3.3 Metric（指标）

```python
class Metric:
    key: str        # 指标名（如 "auc", "accuracy", "f1"）
    value: float    # 指标值
    timestamp: int  # 记录时间戳
    step: int       # 训练步数（支持时间序列）
```

### 3.4 MLagent_v2 实验映射

| MLflow 实体 | MLagent_v2 映射 | 示例 |
|------------|----------------|------|
| `Experiment` | 项目/任务 | "NGS-CNS-Methylation-v1" |
| `Run` | 单次实验 | "run-042: 50-features-XGBoost" |
| `Param` | 实验参数 | `{"n_estimators": 200, "max_depth": 6}` |
| `Metric` | 性能指标 | `{"auc": 0.884, "accuracy": 0.82}` |
| `Artifact` | 模型/代码/图表 | `model.pkl`, `feature_importance.png` |
| `Tag` | 元数据标签 | `{"feature_count": "50", "source": "agent"}` |
| `PromptVersion` | SKILL Prompt | `"ngs-feature-prompt" v3` |
| `Trace` | LLM 调用记录 | "选择特征组合的推理链" |

---

## 4. 扩展点

### 4.1 自定义 autolog 集成

为 NGS 特化工具库（如 pysam、biopython）编写 autolog 插件：

```python
from mlflow.utils.autologging_utils import autologging_integration

@autologging_integration("ngs_tools")
def autolog_ngs(log_models=True, log_datasets=True, disable=False):
    """自动记录 NGS 工具调用参数和结果"""
```

### 4.2 工件存储可替换

开发用本地文件系统，生产用云存储：

```python
import mlflow
mlflow.set_tracking_uri("postgresql://...")
mlflow.set_artifact_uri("s3://my-bucket/mlflow/")
```

### 4.3 追踪导出器可配置

OpenTelemetry 追踪可导出到 Jaeger、Zipkin 或 MLflow 内置 UI：

```python
from mlflow.tracing.provider import _get_trace_exporter
# 自定义导出器配置
```

### 4.4 实验搜索过滤

支持类 SQL 的过滤表达式：

```python
runs = client.search_runs(
    experiment_ids=["1"],
    filter_string="metrics.auc > 0.85 and params.model = 'xgboost'",
    order_by=["metrics.auc DESC"],
)
```

### 4.5 REST API 与 MCP Server 封装

MLflow 提供完整的 REST API，可封装为 MCP server 供 Claude Agent SDK 调用：

```python
# MCP Tool: query_mlflow_experiments
@tool
def query_mlflow_experiments(filter_string: str, top_k: int = 5) -> str:
    """查询 MLflow 实验历史"""
    client = MlflowClient()
    runs = client.search_runs(experiment_ids=["1"], filter_string=filter_string)
    return format_runs_for_agent(runs[:top_k])
```

---

## 5. 改造成本估算

### 5.1 改造范围（pip install → MLagent_v2 实验追踪层）

| 改造项 | 工作量 | 风险 | 说明 |
|--------|--------|------|------|
| **pip install + 本地部署** | 0.5 人天 | 极低 | `pip install mlflow`, `mlflow ui --port 5000` |
| **autolog 集成** | 1-2 人天 | 低 | 在训练脚本中插入 `mlflow.sklearn.autolog()` |
| **Agent 循环中手动 log** | 1-2 人天 | 低 | 在探索循环中插入 `log_metric` / `log_param` |
| **与 mem0 联合查询** | 2-3 人天 | 中 | 设计"mem0 语义检索 → MLflow 精确查询"接口 |
| **Prompt 注册表集成** | 2-3 人天 | 低 | SKILL Prompt 版本化管理 |
| **Tracing 集成** | 2-3 人天 | 中 | 记录 Agent LLM 调用链路 |
| **自定义 NGS autolog** | 3-5 人天 | 中 | 为 NGS 工具库编写 autolog 插件 |
| **测试与验证** | 2-3 人天 | 低 | 端到端实验记录验证 |

### 5.2 总估算

- **工作量**：13-21 人天（约 2-4 周，1 名工程师）
- **核心风险**：
  1. 高频实验记录（50+ 轮/小时）可能导致 FileStore 性能瓶颈（缓解：切换到 SQLStore）
  2. autolog 对自定义 NGS 工具无覆盖（需自行编写插件）
  3. Prompt Registry 是 3.x 新功能，API 可能变动

---

## 6. 致命缺陷自述（强制）

### 缺陷 1：无 Agent 循环能力——纯追踪工具，不做任何自动化决策

**问题**：MLflow 是"记录工具"而非"决策工具"。它：
- 不决定下一步实验该尝试什么特征组合
- 不从历史实验中"学习"或"推理"
- 不提供语义检索（只能按 key=value 过滤，不能"找相似实验"）

**源码证据**：MLflow 的 `search_runs()` 使用 filter_string 做精确匹配：
```python
runs = client.search_runs(
    filter_string="metrics.auc > 0.85 and params.model = 'xgboost'"
)
```

无法表达"找与当前甲基化分类任务相似的历史实验"这种语义查询。

**对 MLagent_v2 的影响**：MLflow 必须与 mem0 配合使用——mem0 负责"语义检索相似实验"，MLflow 负责"返回该实验的精确指标"。单独使用 MLflow 无法满足"经验复用"需求。

### 缺陷 2：本地 FileStore 不适合高频写入

**问题**：默认 FileStore 将每个 metric/param 写入独立文件。高频场景（50+ 轮实验/小时，每轮 20+ 指标）下：
- 文件系统压力增大（数千个小文件）
- `search_runs()` 性能下降（需扫描大量目录）
- 无内置缓存机制

**对 MLagent_v2 的影响**：探索模式下高频实验记录可能导致 MLflow UI 响应变慢。缓解方案：
- 切换到 SQLStore（PostgreSQL/SQLite）
- 批量聚合后写入（而非每轮实时写入）
- 异步写入（`MLFLOW_ENABLE_ASYNC_LOGGING=true`）

### 缺陷 3：Prompt Registry 生态不成熟

**问题**：MLflow 的 Prompt Registry 是 3.x 引入的新功能：
- 文档和示例较少
- API 可能在后续版本中变动
- 与 LangChain/LangGraph 的 Prompt 管理生态存在竞争
- 开源社区对 Prompt Registry 的采用率尚低

**对 MLagent_v2 的影响**：若将 SKILL.md 的 Prompt 管理迁移到 MLflow Prompt Registry，存在 API 变动风险。建议：
- 初期 SKILL Prompt 仍用文件系统管理（`.claude/skills/`）
- MLflow Prompt Registry 作为可选增强，而非强制依赖
- 封装抽象层隔离 MLflow Prompt API 的变动

---

## 7. 与其他候选项目的集成可行性

### 7.1 vs mem0（记忆系统）—— 必须集成，双层互补

mem0（语义记忆）+ MLflow（结构化追踪）构成完整的"经验记忆库"：

```
Agent 查询："甲基化分类的有效特征"
    ↓
mem0.search("甲基化分类的有效特征") → 返回语义相似的记忆列表
    ↓
每条记忆携带 metadata: {"experiment_id": "42", "run_id": "run-123"}
    ↓
MLflow 查询：client.get_run("run-123") → 返回精确指标 {auc: 0.88, features: [...]}
```

**集成成本**：约 1-2 人天（设计联合查询接口）。无依赖冲突（均使用 pydantic v2、sqlalchemy 2.x）。

### 7.2 vs AIDE（探索引擎）—— 可配合，数据流天然对齐

AIDE 的评估循环输出 Python dict（如 `{"auc": 0.88}`），MLflow 的 `log_metrics()` 直接接收 dict：

```python
# AIDE 的 benchmark 函数中插入
import mlflow
mlflow.log_metrics({"auc": result["auc"], "accuracy": result["accuracy"]})
mlflow.log_params({"feature_count": len(features), "model": "xgboost"})
```

**集成成本**：极低，约 0.5 人天。

### 7.3 vs CAAFE（特征工程）—— 可配合，记录特征工程历史

CAAFE 的每轮迭代结果可写入 MLflow：

```python
mlflow.log_metric("caafe_roc_improvement", improvement_roc)
mlflow.log_param("caafe_iteration", i)
mlflow.log_artifact("caafe_generated_code.py", caafe_clf.code)
```

### 7.4 vs Notebook Intelligence（Jupyter 集成）—— 可配合，数据流正交

NBI 管理 notebook 执行，MLflow 记录执行结果。两者通过 `mlflow.start_run()` 关联：
- NBI 执行 notebook cell → 训练脚本内 `mlflow.autolog()` 记录
- MLflow Run 与 notebook 文件名关联（通过 tag）

### 7.5 vs OpenFE / Featuretools（特征工具）—— 无直接关系

特征工具的结果可通过 MLflow 记录（特征数量、生成时间、性能提升），但无直接代码级集成。

---

## 8. 结论

MLflow 是 MLagent_v2 实验追踪层的**行业标准选择**，理由如下：

1. **26K Stars + Apache-2.0**：ML 实验追踪领域的事实标准，生态最成熟
2. **双层 API 设计**：Fluent API 适合脚本内嵌，Client API 适合程序化查询
3. **60+ 框架 autolog**：sklearn/XGBoost 训练零代码记录
4. **四位一体**：实验追踪 + 模型注册 + Prompt 注册 + OpenTelemetry 追踪
5. **零配置本地部署**：`mlflow ui --port 5000` 即可使用
6. **与 mem0 完美互补**：mem0 提供语义检索，MLflow 提供结构化精确查询

核心改造集中在：
1. 在 Agent 探索循环中插入 `log_metric` / `log_param` 调用
2. 设计 mem0 → MLflow 的联合查询接口（语义→结构化）
3. 评估 Prompt Registry 的采用时机（建议初期观望）

这三项改造工作量可控（13-21 人天），且 MLflow 的模块化架构确保所有存储后端（File/SQL/云存储）均可按需切换。MLflow 是 MLagent_v2 实验追踪层的最优选择。
