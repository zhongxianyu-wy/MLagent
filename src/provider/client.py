from __future__ import annotations

import json
import os
import re
from collections.abc import Callable
from pathlib import Path
from urllib.error import HTTPError
from urllib import request

from src.models import LLMProviderConfig

Transport = Callable[[str, dict, dict, int], dict]


class LLMClient:
    def __init__(
        self,
        config: LLMProviderConfig,
        transport: Transport | None = None,
    ) -> None:
        self.config = config
        self.base_url = config.base_url
        self.default_model = config.model
        self.small_model = config.small_model
        self.max_tokens = config.max_tokens
        self.timeout_sec = config.timeout_sec
        raw_api_key = os.environ.get(config.api_key_env) or _read_env_value(
            Path(".env"), config.api_key_env
        )
        self.api_key = _resolve_api_key(raw_api_key)
        self.transport = transport or _post_json

    def stream(self, prompt: str):
        if not self.api_key:
            yield f"API key environment variable {self.config.api_key_env} is not set."
            return
        if self.config.api_protocol == "openai-completions":
            yield from self._stream_openai_completions(prompt)
            return
        yield from self._stream_anthropic_messages(prompt)

    def _stream_anthropic_messages(self, prompt: str):
        payload = {
            "model": self.default_model,
            "max_tokens": self.max_tokens,
            "messages": [
                {"role": "user", "content": [{"type": "text", "text": prompt}]}
            ],
        }
        headers = {
            "content-type": "application/json",
            "anthropic-version": "2023-06-01",
            "X-Api-Key": self.api_key,
        }
        try:
            response = self.transport(
                f"{self.base_url.rstrip('/')}/v1/messages",
                payload,
                headers,
                self.timeout_sec,
            )
        except HTTPError as exc:
            yield f"LLM request failed with HTTP {exc.code}: {exc.reason}"
            return
        for item in response.get("content", []):
            if item.get("type") == "text":
                yield item.get("text", "")

    def _stream_openai_completions(self, prompt: str):
        payload = {
            "model": self.default_model,
            "max_tokens": self.max_tokens,
            "messages": [{"role": "user", "content": prompt}],
        }
        headers = {
            "content-type": "application/json",
            "Authorization": f"Bearer {self.api_key}",
        }
        try:
            response = self.transport(
                f"{self.base_url.rstrip('/')}/chat/completions",
                payload,
                headers,
                self.timeout_sec,
            )
        except HTTPError as exc:
            yield f"LLM request failed with HTTP {exc.code}: {exc.reason}"
            return
        for choice in response.get("choices", []):
            content = choice.get("message", {}).get("content")
            if content:
                yield _strip_reasoning_tags(content)


def _post_json(url: str, payload: dict, headers: dict, timeout: int) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(url, data=data, headers=headers, method="POST")
    with request.urlopen(req, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def _read_env_value(path: Path, key: str) -> str | None:
    if not path.exists():
        return None
    for raw_line in path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        current_key, value = line.split("=", 1)
        if current_key.strip() == key:
            return value.strip().strip('"').strip("'")
    return None


def _resolve_api_key(value: str | None) -> str | None:
    if value is None:
        return None
    return os.environ.get(value) or _read_env_value(Path(".env"), value) or value


def _strip_reasoning_tags(content: str) -> str:
    return re.sub(r"<think>.*?</think>", "", content, flags=re.DOTALL).strip()
