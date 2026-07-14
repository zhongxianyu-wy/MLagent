from src.models import (
    ApprovedSkill,
    DatasetManifest,
    EvaluationConfig,
    ExperimentRoundTrace,
    ExperimentRun,
    LLMProviderConfig,
    MemoryEntry,
    ResearchArtifact,
    RunControlPolicy,
    SafetyDecision,
    SkillCandidate,
    TrackingRecord,
)
from src.provider.client import LLMClient
from src.provider.config import load_provider_config
from urllib.error import HTTPError


def test_dataset_manifest_requires_explicit_binary_labels():
    manifest = DatasetManifest(
        dataset_id="ds-1",
        source_paths=["raw/features.csv", "raw/labels.csv"],
        sample_id_col="sample_id",
        label_col="group",
        positive_label="case",
        negative_label="control",
        train_feature_path="experiments/standardized/ds-1/train_features.csv",
        train_label_path="experiments/standardized/ds-1/train_labels.csv",
        test_feature_path=None,
        test_label_path=None,
        split_strategy="train_only",
        split_ratio=None,
        random_seed=None,
        notes="fixture",
    )

    assert manifest.positive_label == "case"
    assert manifest.negative_label == "control"


def test_run_control_and_evaluation_config_capture_stop_and_threshold_rules():
    policy = RunControlPolicy(
        target_metric_name="sensitivity_at_specificity",
        target_metric_value=0.9,
        max_iterations=10,
        max_runtime_minutes=120,
        patience_rounds=3,
        min_delta=0.001,
        user_stoppable=True,
    )
    evaluation = EvaluationConfig(
        metric="sensitivity_at_specificity",
        k_folds=5,
        target_specificity=0.95,
        threshold_policy="target_specificity",
        use_test_if_available=True,
    )

    assert policy.max_iterations == 10
    assert evaluation.threshold_policy == "target_specificity"
    assert evaluation.target_specificity == 0.95


def test_experiment_run_and_round_trace_preserve_frontend_state():
    run = ExperimentRun(
        experiment_id="exp-1",
        mode="exploration",
        dataset_id="ds-1",
        status="running",
        run_control_policy_id="policy-1",
        started_at=1,
        ended_at=None,
        stop_reason=None,
    )
    trace = ExperimentRoundTrace(
        round_id="round-1",
        experiment_id="exp-1",
        round_num=1,
        mode="exploration",
        exploration_direction="try variance-filtered methylation features",
        hypothesis="variance filtering improves AUC",
        preprocessing_strategy="zscore",
        feature_subset_strategy="variance_threshold",
        selected_features_json='["cg1", "cg2"]',
        model_type="xgboost",
        params_json='{"n_estimators": 100}',
        cv_metrics_json='{"auc_mean": 0.82}',
        threshold_policy="youden",
        selected_threshold=0.42,
        test_metrics_json=None,
        guidance_metric_name="auc",
        guidance_metric_value=0.82,
        status="completed",
        stop_reason=None,
        error_msg=None,
        llm_rationale_summary="low variance features are likely noise",
        created_at=2,
    )

    assert run.status == "running"
    assert trace.guidance_metric_value == 0.82
    assert trace.llm_rationale_summary


def test_memory_skill_research_provider_safety_and_tracking_models_link_ids():
    memory = MemoryEntry(
        memory_id="mem-1",
        source="agent",
        text="variance filtering improved AUC",
        linked_experiment_id="exp-1",
        linked_round_id="round-1",
        linked_skill_id=None,
        confidence="medium",
        needs_review=False,
        created_at=3,
    )
    candidate = SkillCandidate(
        candidate_id="cand-1",
        source_type="best_run",
        source_ref="round-1",
        skill_name="variance-filter-xgboost",
        draft_path="experiments/outputs/exp-1/SKILL.md",
        validation_status="pending",
        darwin_iteration_status="not_started",
        review_status="pending",
        approved_skill_id=None,
        created_at=4,
        updated_at=4,
    )
    skill = ApprovedSkill(
        skill_id="skill-1",
        name="variance-filter-xgboost",
        path=".claude/skills/variance-filter-xgboost/SKILL.md",
        description="Variance-filtered XGBoost workflow",
        applicability="binary methylation matrices",
        version="0.1.0",
        created_from_candidate_id="cand-1",
        last_used_at=None,
    )
    artifact = ResearchArtifact(
        artifact_id="art-1",
        research_job_id="job-1",
        source_url="https://example.com/paper",
        source_type="paper",
        method_summary="method",
        feature_engineering_notes="notes",
        model_notes="model",
        evaluation_notes="eval",
        reference_code_notes="code",
        limitations="limits",
        created_at=5,
    )
    provider = LLMProviderConfig(
        provider_name="anthropic-compatible",
        base_url="https://api.example.com",
        api_key_env="MODEL_API_KEY",
        model="glm-coding-plan",
        small_model=None,
        max_tokens=4096,
        timeout_sec=120,
    )
    safety = SafetyDecision(
        allowed=False,
        reason="blocked destructive command",
        blocked_pattern="rm -rf",
        requires_user_approval=False,
    )
    tracking = TrackingRecord(
        tracking_id="track-1",
        round_id="round-1",
        experiment_id="exp-1",
        mlflow_run_id=None,
        artifact_paths=["experiments/models/exp-1/model.json"],
        logged_at=6,
        status="pending",
        error_msg=None,
    )

    assert memory.linked_round_id == candidate.source_ref
    assert skill.created_from_candidate_id == candidate.candidate_id
    assert artifact.source_type == "paper"
    assert provider.model == "glm-coding-plan"
    assert safety.allowed is False
    assert tracking.round_id == "round-1"


def test_provider_config_loads_anthropic_compatible_environment(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("ANTHROPIC_BASE_URL", raising=False)
    monkeypatch.delenv("ANTHROPIC_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_DEFAULT_SONNET_MODEL", raising=False)
    monkeypatch.delenv("ANTHROPIC_AUTH_TOKEN", raising=False)
    monkeypatch.delenv("API_TIMEOUT_MS", raising=False)
    monkeypatch.setenv("MLAGENT_LLM_PROVIDER_NAME", "anthropic-compatible")
    monkeypatch.setenv("MLAGENT_LLM_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("MLAGENT_LLM_API_KEY_ENV", "MODEL_API_KEY")
    monkeypatch.setenv("MLAGENT_LLM_MODEL", "glm-coding-plan")
    monkeypatch.setenv("MLAGENT_LLM_SMALL_MODEL", "glm-coding-flash")
    monkeypatch.setenv("MLAGENT_LLM_MAX_TOKENS", "2048")
    monkeypatch.setenv("MLAGENT_LLM_TIMEOUT_SEC", "60")

    config = load_provider_config()

    assert config.provider_name == "anthropic-compatible"
    assert config.base_url == "https://api.example.com"
    assert config.api_key_env == "MODEL_API_KEY"
    assert config.model == "glm-coding-plan"
    assert config.small_model == "glm-coding-flash"
    assert config.max_tokens == 2048
    assert config.timeout_sec == 60


def test_provider_config_loads_local_env_file_when_process_env_missing(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MLAGENT_LLM_PROVIDER_NAME", raising=False)
    monkeypatch.delenv("MLAGENT_LLM_BASE_URL", raising=False)
    monkeypatch.delenv("MLAGENT_LLM_API_KEY_ENV", raising=False)
    monkeypatch.delenv("MLAGENT_LLM_MODEL", raising=False)
    monkeypatch.delenv("MLAGENT_LLM_SMALL_MODEL", raising=False)
    monkeypatch.delenv("MLAGENT_LLM_MAX_TOKENS", raising=False)
    monkeypatch.delenv("MLAGENT_LLM_TIMEOUT_SEC", raising=False)
    (tmp_path / ".env").write_text(
        "\n".join(
            [
                "MLAGENT_LLM_PROVIDER_NAME=minimax",
                "MLAGENT_LLM_BASE_URL=https://api.minimaxi.com/anthropic",
                "MLAGENT_LLM_API_KEY_ENV=MINIMAX_API_KEY",
                "MLAGENT_LLM_MODEL=MiniMax-M2.7",
                "MLAGENT_LLM_SMALL_MODEL=MiniMax-M2.7-highspeed",
                "MLAGENT_LLM_MAX_TOKENS=1024",
                "MLAGENT_LLM_TIMEOUT_SEC=30",
            ]
        )
    )

    config = load_provider_config()

    assert config.provider_name == "minimax"
    assert config.base_url == "https://api.minimaxi.com/anthropic"
    assert config.api_key_env == "MINIMAX_API_KEY"
    assert config.model == "MiniMax-M2.7"
    assert config.small_model == "MiniMax-M2.7-highspeed"
    assert config.max_tokens == 1024
    assert config.timeout_sec == 30


def test_provider_config_prefers_anthropic_compatible_official_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
    monkeypatch.setenv("ANTHROPIC_MODEL", "MiniMax-M2.7")
    monkeypatch.setenv("ANTHROPIC_DEFAULT_SONNET_MODEL", "MiniMax-M2.7")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "secret")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "MINIMAX_API_KEY")
    monkeypatch.setenv("API_TIMEOUT_MS", "3000000")
    monkeypatch.setenv("MLAGENT_LLM_BASE_URL", "https://api.example.com")
    monkeypatch.setenv("MLAGENT_LLM_MODEL", "wrong-model")

    config = load_provider_config()

    assert config.provider_name == "anthropic-compatible"
    assert config.base_url == "https://api.minimaxi.com/anthropic"
    assert config.api_key_env == "ANTHROPIC_API_KEY"
    assert config.model == "MiniMax-M2.7"
    assert config.small_model == "MiniMax-M2.7"
    assert config.timeout_sec == 3000


def test_provider_config_openai_completions_overrides_anthropic_env(monkeypatch):
    monkeypatch.setenv("MLAGENT_LLM_API_PROTOCOL", "openai-completions")
    monkeypatch.setenv("MLAGENT_LLM_PROVIDER_NAME", "kimi-code")
    monkeypatch.setenv("MLAGENT_LLM_BASE_URL", "https://api.kimi.com/v1")
    monkeypatch.setenv("MLAGENT_LLM_API_KEY_ENV", "KIMI_API_KEY")
    monkeypatch.setenv("MLAGENT_LLM_MODEL", "kimi-for-coding")
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://api.minimaxi.com/anthropic")
    monkeypatch.setenv("ANTHROPIC_MODEL", "MiniMax-M2.7")

    config = load_provider_config()

    assert config.provider_name == "kimi-code"
    assert config.base_url == "https://api.kimi.com/v1"
    assert config.api_key_env == "KIMI_API_KEY"
    assert config.model == "kimi-for-coding"
    assert config.api_protocol == "openai-completions"


def test_provider_config_supports_minimax_openai_completions(monkeypatch):
    monkeypatch.setenv("MLAGENT_LLM_API_PROTOCOL", "openai-completions")
    monkeypatch.setenv("MLAGENT_LLM_PROVIDER_NAME", "minimax")
    monkeypatch.setenv("MLAGENT_LLM_BASE_URL", "https://api.minimaxi.com/v1")
    monkeypatch.setenv("MLAGENT_LLM_API_KEY_ENV", "MINIMAX_API_KEY")
    monkeypatch.setenv("MLAGENT_LLM_MODEL", "MiniMax-M2.7")

    config = load_provider_config()

    assert config.provider_name == "minimax"
    assert config.base_url == "https://api.minimaxi.com/v1"
    assert config.api_key_env == "MINIMAX_API_KEY"
    assert config.model == "MiniMax-M2.7"
    assert config.api_protocol == "openai-completions"


def test_llm_client_exposes_request_defaults_without_api_key(monkeypatch):
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    config = LLMProviderConfig(
        provider_name="anthropic-compatible",
        base_url="https://api.example.com",
        api_key_env="MODEL_API_KEY",
        model="glm-coding-plan",
        small_model="glm-coding-flash",
        max_tokens=2048,
        timeout_sec=60,
    )

    client = LLMClient(config)

    assert client.default_model == "glm-coding-plan"
    assert client.small_model == "glm-coding-flash"
    assert client.base_url == "https://api.example.com"
    assert client.api_key is None


def test_llm_client_stream_posts_anthropic_messages_request(monkeypatch):
    requests = []

    def fake_transport(url, payload, headers, timeout):
        requests.append((url, payload, headers, timeout))
        return {
            "content": [
                {"type": "text", "text": "你好"},
                {"type": "text", "text": "，我已连接"},
            ]
        }

    monkeypatch.setenv("MODEL_API_KEY", "secret")
    config = LLMProviderConfig(
        provider_name="minimax",
        base_url="https://api.minimaxi.com/anthropic",
        api_key_env="MODEL_API_KEY",
        model="MiniMax-M2.7",
        small_model="MiniMax-M2.7-highspeed",
        max_tokens=1024,
        timeout_sec=30,
    )
    client = LLMClient(config, transport=fake_transport)

    chunks = list(client.stream("你好"))

    assert chunks == ["你好", "，我已连接"]
    assert requests[0][0] == "https://api.minimaxi.com/anthropic/v1/messages"
    assert requests[0][1]["model"] == "MiniMax-M2.7"
    assert requests[0][1]["messages"] == [
        {
            "role": "user",
            "content": [{"type": "text", "text": "你好"}],
        }
    ]
    assert requests[0][2]["X-Api-Key"] == "secret"


def test_llm_client_stream_posts_openai_chat_completions_request(monkeypatch):
    requests = []

    def fake_transport(url, payload, headers, timeout):
        requests.append((url, payload, headers, timeout))
        return {"choices": [{"message": {"content": "ok"}}]}

    monkeypatch.setenv("KIMI_API_KEY", "secret")
    config = LLMProviderConfig(
        provider_name="kimi-code",
        base_url="https://api.kimi.com/v1",
        api_key_env="KIMI_API_KEY",
        model="kimi-for-coding",
        small_model=None,
        max_tokens=1024,
        timeout_sec=30,
        api_protocol="openai-completions",
    )
    client = LLMClient(config, transport=fake_transport)

    chunks = list(client.stream("你好"))

    assert chunks == ["ok"]
    assert requests[0][0] == "https://api.kimi.com/v1/chat/completions"
    assert requests[0][1]["model"] == "kimi-for-coding"
    assert requests[0][1]["messages"] == [{"role": "user", "content": "你好"}]
    assert requests[0][2]["Authorization"] == "Bearer secret"
    assert "X-Api-Key" not in requests[0][2]


def test_llm_client_stream_strips_openai_reasoning_tags(monkeypatch):
    def fake_transport(url, payload, headers, timeout):
        return {
            "choices": [
                {"message": {"content": "<think>internal reasoning</think>\n\nok"}}
            ]
        }

    monkeypatch.setenv("MINIMAX_API_KEY", "secret")
    config = LLMProviderConfig(
        provider_name="minimax",
        base_url="https://api.minimaxi.com/v1",
        api_key_env="MINIMAX_API_KEY",
        model="MiniMax-M2.7",
        small_model=None,
        max_tokens=1024,
        timeout_sec=30,
        api_protocol="openai-completions",
    )
    client = LLMClient(config, transport=fake_transport)

    assert list(client.stream("请只回复 ok")) == ["ok"]


def test_llm_client_reads_api_key_from_local_env_file(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("MODEL_API_KEY", raising=False)
    (tmp_path / ".env").write_text("MODEL_API_KEY=secret-from-file\n")
    config = LLMProviderConfig(
        provider_name="minimax",
        base_url="https://api.minimaxi.com/anthropic",
        api_key_env="MODEL_API_KEY",
        model="MiniMax-M2.7",
        small_model=None,
        max_tokens=1024,
        timeout_sec=30,
    )

    client = LLMClient(config)

    assert client.api_key == "secret-from-file"


def test_llm_client_resolves_anthropic_auth_token_indirection(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "MINIMAX_API_KEY")
    monkeypatch.setenv("MINIMAX_API_KEY", "secret-token")
    config = LLMProviderConfig(
        provider_name="anthropic-compatible",
        base_url="https://api.minimaxi.com/anthropic",
        api_key_env="ANTHROPIC_AUTH_TOKEN",
        model="MiniMax-M2.7",
        small_model=None,
        max_tokens=1024,
        timeout_sec=30,
    )

    client = LLMClient(config)

    assert client.api_key == "secret-token"


def test_llm_client_stream_returns_message_on_http_error(monkeypatch):
    def failing_transport(url, payload, headers, timeout):
        raise HTTPError(url=url, code=401, msg="Unauthorized", hdrs={}, fp=None)

    monkeypatch.setenv("MODEL_API_KEY", "secret")
    config = LLMProviderConfig(
        provider_name="minimax",
        base_url="https://api.minimaxi.com/anthropic",
        api_key_env="MODEL_API_KEY",
        model="MiniMax-M2.7",
        small_model=None,
        max_tokens=1024,
        timeout_sec=30,
    )
    client = LLMClient(config, transport=failing_transport)

    assert list(client.stream("hello")) == ["LLM request failed with HTTP 401: Unauthorized"]
