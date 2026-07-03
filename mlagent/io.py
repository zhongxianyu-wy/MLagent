"""I/O helpers: YAML (timestamps kept as strings), text, hashing."""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml

# PyYAML's SafeLoader auto-parses bare ISO timestamps into datetime; our schemas store
# timestamps as str, so drop the timestamp resolver to keep them as strings.
_TIMESTAMP_TAG = "tag:yaml.org,2002:timestamp"


class _SafeLoaderNoTimestamp(yaml.SafeLoader):
    pass


_SafeLoaderNoTimestamp.yaml_implicit_resolvers = {
    char: [entry for entry in resolvers if entry[0] != _TIMESTAMP_TAG]
    for char, resolvers in yaml.SafeLoader.yaml_implicit_resolvers.items()
}


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def read_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = yaml.load(handle, Loader=_SafeLoaderNoTimestamp) or {}
    if not isinstance(data, dict):
        raise ValueError(f"YAML root must be mapping: {path}")
    return data


def write_yaml(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        yaml.safe_dump(data, handle, sort_keys=False, allow_unicode=False)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()
