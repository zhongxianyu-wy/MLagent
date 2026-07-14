from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Iterable


@dataclass(frozen=True)
class ApiResponse:
    status_code: int
    json: object | None = None
    stream: Iterable[str] | None = None
    media_type: str = "application/json"
