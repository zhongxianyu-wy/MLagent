from __future__ import annotations

from typing import Protocol


class AIDEProvider(Protocol):
    def propose(self, request: dict) -> dict:
        ...


class AIDERoutingAdapter:
    ALLOWED_KEYS = {"dataset_summary", "objective", "budget", "context_ids"}

    def __init__(self, provider: AIDEProvider) -> None:
        self.provider = provider

    def propose(self, request: dict) -> dict:
        bounded_request = {
            key: request[key] for key in self.ALLOWED_KEYS if key in request
        }
        return self.provider.propose(bounded_request)
