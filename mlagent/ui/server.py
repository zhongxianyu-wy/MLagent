"""MLagent UI backend (FastAPI).

Serves the frontend + REST API for F1 (code review) and F2 (memory boards).
The memory root is set via MLAGENT_MEMORY_ROOT env var at launch.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, JSONResponse

from mlagent.io import read_text, read_yaml

_MEMORY_ROOT = Path(os.environ.get("MLAGENT_MEMORY_ROOT", "project_memory"))

app = FastAPI(title="MLagent UI", docs_url=None, redoc_url=None)


def _safe_read_yaml(path: Path) -> dict[str, Any]:
    return read_yaml(path) if path.exists() else {}


# --- F0: health + static ---


@app.get("/api/health")
async def health() -> JSONResponse:
    return JSONResponse({"status": "ok"}, headers={"x-mlagent-ui": "true"})


@app.get("/")
async def index() -> HTMLResponse:
    static = Path(__file__).parent / "static" / "index.html"
    return HTMLResponse(static.read_text(encoding="utf-8"))


# --- F2: memory boards ---


@app.get("/api/status")
async def get_status() -> dict[str, Any]:
    from mlagent.repo import memory_status
    try:
        return memory_status(_MEMORY_ROOT)
    except Exception:
        return {"error": "no memory repo"}


@app.get("/api/experience")
async def get_experience() -> list[dict[str, Any]]:
    """All experience entries (for F2 经验看板)."""
    results: list[dict[str, Any]] = []
    exp_root = _MEMORY_ROOT / "experience"
    if not exp_root.exists():
        return results
    for path in sorted(exp_root.rglob("*.yaml")):
        data = read_yaml(path)
        results.append({
            "id": data.get("id"),
            "type": data.get("type"),
            "summary": data.get("summary", ""),
            "confidence": data.get("confidence"),
            "needs_review": data.get("needs_review"),
            "applies_when": data.get("applies_when", []),
            "superseded_by": data.get("superseded_by"),
            "created_at": data.get("created_at"),
        })
    return results


@app.get("/api/sops")
async def get_sops() -> dict[str, Any]:
    from mlagent.sop import list_sops
    try:
        return list_sops(_MEMORY_ROOT)
    except Exception:
        return {"approved": [], "candidates": []}


@app.get("/api/sop/{sop_name}/{version}")
async def get_sop_detail(sop_name: str, version: str) -> dict[str, Any]:
    from mlagent.sop import get_sop
    try:
        bundle = get_sop(_MEMORY_ROOT, sop_name, version, include_draft=True)
        return {"name": sop_name, "version": version, "source": bundle["source"],
                "state": bundle["state"], "sop": bundle["sop"]}
    except Exception as exc:
        return {"error": str(exc)}


@app.get("/api/runs")
async def get_runs() -> list[dict[str, Any]]:
    """Raw memory runs (for F2 探索趋势看板)."""
    results: list[dict[str, Any]] = []
    for subdir in ("sessions", "explorations", "runs", "human_notes"):
        d = _MEMORY_ROOT / "raw_memory" / subdir
        if not d.exists():
            continue
        for path in sorted(d.glob("*.yaml")):
            data = read_yaml(path)
            results.append({
                "id": data.get("id"),
                "type": data.get("type"),
                "created_at": data.get("created_at"),
                "goal": data.get("goal"),
                "results": data.get("results", {}),
                "conclusion": data.get("conclusion"),
            })
    return results


@app.get("/api/search")
async def search(q: str = Query(...)) -> dict[str, Any]:
    """Keyword search across experience + raw + SOPs (for F2 关键词检索看板)."""
    q_lower = q.lower()
    matches: list[dict[str, Any]] = []
    # experience
    exp_root = _MEMORY_ROOT / "experience"
    if exp_root.exists():
        for path in sorted(exp_root.rglob("*.yaml")):
            data = read_yaml(path)
            text = (str(data.get("summary", "")) + str(data.get("detail", "")) + " ".join(data.get("applies_when", []))).lower()
            if q_lower in text:
                matches.append({"kind": "experience", "id": data.get("id"), "type": data.get("type"),
                                "summary": data.get("summary"), "path": str(path.relative_to(_MEMORY_ROOT))})
    # raw
    raw_root = _MEMORY_ROOT / "raw_memory"
    if raw_root.exists():
        for path in sorted(raw_root.rglob("*.yaml")):
            data = read_yaml(path)
            text = (str(data.get("goal", "")) + str(data.get("hypothesis", ""))).lower()
            if q_lower in text:
                matches.append({"kind": "raw", "id": data.get("id"), "type": data.get("type"),
                                "summary": data.get("goal"), "path": str(path.relative_to(_MEMORY_ROOT))})
    return {"query": q, "results": matches}


# --- F1: code review ---


@app.get("/api/script")
async def get_script(path: str = Query(...)) -> dict[str, Any]:
    """Read a script + its manifest for F1 structured code view."""
    p = Path(path)
    manifest = p.with_suffix(".manifest.yaml")
    return {
        "path": path,
        "code": read_text(p) if p.exists() else "",
        "manifest": _safe_read_yaml(manifest) if manifest.exists() else {"steps": []},
    }
