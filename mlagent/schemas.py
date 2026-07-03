"""Pydantic schemas for the three-layer memory system (v0.3 clarified design).

Layers: raw_memory (evidence + conclusion) / experience (distilled, incl. conventions) /
skill_library (versioned SOP-skills with a strict gate). Lineage + review/maturity
fields are first-class so everything is traceable.
"""

from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

# --- conclusion (exploration verdict; "explore to conclusion" made explicit) ---


class Conclusion(BaseModel):
    hypothesis: str
    outcome: Literal["confirmed", "refuted", "inconclusive"]
    summary: str = ""
    evidence: list[str] = Field(default_factory=list)


# --- shared / nested ---


class RawCommand(BaseModel):
    command: str
    summary: str = ""
    status: Literal["success", "failed"]


class HumanReview(BaseModel):
    reviewed: bool
    reviewer: str | None = None
    reviewed_at: str | None = None
    approval_note: str | None = None


class PrimaryMetric(BaseModel):
    name: str = Field(min_length=1)
    value: float

    @field_validator("value")
    @classmethod
    def _finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("metric value must be finite (not NaN or inf)")
        return v


class BenchmarkMetric(PrimaryMetric):
    pass


class Performance(BaseModel):
    primary_metric: PrimaryMetric
    dataset_version: str = Field(min_length=1)
    validation_protocol: str = Field(min_length=1)
    benchmark_metric: BenchmarkMetric | None = None
    target_or_acceptance_note: str | None = None


class AcceptanceGate(BaseModel):
    metric: str = Field(min_length=1)
    min_value: float
    tolerance: float = 0.0


class Gate(BaseModel):
    """Strict promotion gate for a SOP version (retrain = deterministic reproduction)."""

    tests_passed: bool = False
    test_command: str = ""
    test_log: str = ""
    acceptance_gate: AcceptanceGate | None = None
    verifier_context_id: str = ""  # != author agent (no self-grade)
    head_sha: str = ""


# --- layer 1: raw memory (evidence + conclusion) ---


class ProjectProfile(BaseModel):
    project_name: str
    task_type: str = "tabular_ml"
    primary_metric: str = "auc"
    memory_version: str = "0.1.0"


class RawMemoryRecord(BaseModel):
    id: str
    type: Literal["session", "exploration", "run", "human_note"]
    created_at: str
    session_id: str | None = None
    goal: str | None = None
    hypothesis: str | None = None
    actions: list[str] = Field(default_factory=list)
    changed_files: list[dict[str, str]] = Field(default_factory=list)
    commands: list[RawCommand] = Field(default_factory=list)
    results: dict[str, Any] = Field(default_factory=dict)
    failure_reason: str | None = None
    human_interventions: list[str] = Field(default_factory=list)
    evidence_links: list[str] = Field(default_factory=list)
    next_steps: list[str] = Field(default_factory=list)
    conclusion: Conclusion | None = None


# --- layer 2: experience (distilled; incl. code conventions) ---


class ExperienceRecord(BaseModel):
    id: str
    type: Literal["lesson", "pitfall", "successful_pattern", "failed_direction", "convention"]
    object_type: Literal["experience"] = "experience"
    summary: str
    detail: str = ""
    confidence: Literal["low", "medium", "high"]
    needs_review: bool
    source_raw_records: list[str] = Field(default_factory=list)
    applies_when: list[str] = Field(default_factory=list)
    avoid_when: list[str] = Field(default_factory=list)
    related_methods: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    valid_from: str | None = None
    superseded_by: str | None = None
    created_at: str
    # research-informed traceability / lifecycle fields
    verified: Literal["unverified", "verified", "contradicted", "rolled_back"] = "unverified"
    maturity: Literal["candidate", "established", "proven", "deprecated"] = "candidate"
    derived_from: list[str] = Field(default_factory=list)  # typed provenance edges (raw://...)
    decision: Literal["insert", "update", "link", "supersede", "noop"] | None = None


# --- layer 3: skill_library (versioned SOP-skill) ---


class SkillVersion(BaseModel):
    version: str
    name: str
    object_type: Literal["skill_version"] = "skill_version"
    state: Literal["draft", "pending_review", "approved", "rejected", "archived"]
    source_type: Literal["best_run", "ipynb_import", "exploration"]
    source_evidence: list[str] = Field(default_factory=list)
    artifacts: list[dict[str, str]] = Field(default_factory=list)
    requirements: dict[str, Any] = Field(default_factory=dict)
    human_review: HumanReview
    performance: dict[str, Any]
    reproducibility: dict[str, Any] = Field(
        default_factory=lambda: {"entrypoint": "", "required_inputs": [], "expected_outputs": []}
    )
    # version metadata (why this SOP exists) — mandatory for traceability
    background: str = ""
    reason: str = ""
    key_params: dict[str, Any] = Field(default_factory=dict)
    key_optimizations: list[str] = Field(default_factory=list)
    gate: Gate | None = None
    valid_from: str | None = None
    superseded_by: str | None = None

    @model_validator(mode="after")
    def approved_requires_review(self) -> "SkillVersion":
        if self.state == "approved" and not self.human_review.reviewed:
            raise ValueError("approved SkillVersion requires human_review.reviewed=true")
        return self


__all__ = [
    "AcceptanceGate",
    "BenchmarkMetric",
    "Conclusion",
    "ExperienceRecord",
    "Gate",
    "HumanReview",
    "Performance",
    "PrimaryMetric",
    "ProjectProfile",
    "RawCommand",
    "RawMemoryRecord",
    "SkillVersion",
]
