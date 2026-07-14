from __future__ import annotations

import os
from pathlib import Path

from src.models import LLMProviderConfig


def load_provider_config() -> LLMProviderConfig:
    env_file = _read_env_file(Path(".env"))
    api_protocol = _api_protocol(env_file)
    if api_protocol == "openai-completions":
        base_url = _config_value(
            "MLAGENT_LLM_BASE_URL", env_file, "https://api.openai.com/v1"
        )
        model = _config_value("MLAGENT_LLM_MODEL", env_file, "gpt-4.1")
        small_model = _config_value("MLAGENT_LLM_SMALL_MODEL", env_file, "") or None
    else:
        base_url = _official_or_project_value(
            "ANTHROPIC_BASE_URL",
            "MLAGENT_LLM_BASE_URL",
            env_file,
            "https://api.anthropic.com",
        )
        model = _official_or_project_value(
            "ANTHROPIC_MODEL",
            "MLAGENT_LLM_MODEL",
            env_file,
            "claude-sonnet-4-6",
        )
        small_model = (
            _official_or_project_value(
                "ANTHROPIC_DEFAULT_SONNET_MODEL",
                "MLAGENT_LLM_SMALL_MODEL",
                env_file,
                "",
            )
            or None
        )
    timeout_ms = os.environ.get("API_TIMEOUT_MS") or env_file.get("API_TIMEOUT_MS")
    return LLMProviderConfig(
        provider_name=_provider_name(env_file, api_protocol),
        base_url=base_url,
        api_key_env=_api_key_env_name(env_file, api_protocol),
        model=model,
        small_model=small_model,
        max_tokens=int(_config_value("MLAGENT_LLM_MAX_TOKENS", env_file, "8096")),
        timeout_sec=int(int(timeout_ms) / 1000)
        if timeout_ms
        else int(_config_value("MLAGENT_LLM_TIMEOUT_SEC", env_file, "120")),
        api_protocol=api_protocol,
    )


def _config_value(key: str, env_file: dict[str, str], default: str) -> str:
    return os.environ.get(key) or env_file.get(key) or default


def _official_or_project_value(
    official_key: str,
    project_key: str,
    env_file: dict[str, str],
    default: str,
) -> str:
    return (
        os.environ.get(official_key)
        or env_file.get(official_key)
        or os.environ.get(project_key)
        or env_file.get(project_key)
        or default
    )


def _api_protocol(env_file: dict[str, str]) -> str:
    if os.environ.get("MLAGENT_LLM_API_PROTOCOL"):
        return os.environ["MLAGENT_LLM_API_PROTOCOL"]
    if os.environ.get("ANTHROPIC_BASE_URL"):
        return "anthropic-messages"
    return env_file.get("MLAGENT_LLM_API_PROTOCOL") or "anthropic-messages"


def _provider_name(env_file: dict[str, str], api_protocol: str) -> str:
    if api_protocol == "openai-completions":
        return _config_value("MLAGENT_LLM_PROVIDER_NAME", env_file, "openai-compatible")
    if os.environ.get("ANTHROPIC_BASE_URL") or env_file.get("ANTHROPIC_BASE_URL"):
        return "anthropic-compatible"
    return _config_value("MLAGENT_LLM_PROVIDER_NAME", env_file, "anthropic-compatible")


def _api_key_env_name(env_file: dict[str, str], api_protocol: str) -> str:
    if api_protocol == "openai-completions":
        return _config_value("MLAGENT_LLM_API_KEY_ENV", env_file, "OPENAI_API_KEY")
    if os.environ.get("ANTHROPIC_API_KEY") or env_file.get("ANTHROPIC_API_KEY"):
        return "ANTHROPIC_API_KEY"
    if os.environ.get("ANTHROPIC_AUTH_TOKEN") or env_file.get("ANTHROPIC_AUTH_TOKEN"):
        return "ANTHROPIC_AUTH_TOKEN"
    return _config_value("MLAGENT_LLM_API_KEY_ENV", env_file, "ANTHROPIC_API_KEY")


def _read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values = {}
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip().strip('"').strip("'")
    return values
