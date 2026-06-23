from __future__ import annotations

import math
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class ProjectProfile(BaseModel):
    project_name: str
    task_type: str = "tabular_ml"
    primary_metric: str = "auc"
    memory_version: str = "0.1.0"


class RawCommand(BaseModel):
    command: str
    summary: str
    status: Literal["success", "failed"]


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


class ExperienceRecord(BaseModel):
    id: str
    type: Literal["lesson", "pitfall", "successful_pattern", "failed_direction"]
    object_type: Literal["experience"] = "experience"
    summary: str
    detail: str
    confidence: Literal["low", "medium", "high"]
    needs_review: bool
    source_raw_records: list[str]
    applies_when: list[str] = Field(default_factory=list)
    avoid_when: list[str] = Field(default_factory=list)
    related_data_fields: list[str] = Field(default_factory=list)
    related_methods: list[str] = Field(default_factory=list)
    related: list[str] = Field(default_factory=list)
    valid_from: str | None = None
    superseded_by: str | None = None
    created_at: str


class KnowledgeItem(BaseModel):
    id: str
    type: Literal["project_doc", "paper", "method_note", "data_doc"]
    title: str
    original_filename: str
    stored_path: str
    source_path: str
    sha256: str
    imported_at: str
    summary: str = ""
    tags: list[str] = Field(default_factory=list)
    index_status: Literal["pending", "indexed"] = "pending"


class HumanReview(BaseModel):
    reviewed: bool
    reviewer: str | None = None
    reviewed_at: str | None = None
    approval_note: str | None = None


class SkillVersion(BaseModel):
    version: str
    name: str
    object_type: Literal["skill_version"] = "skill_version"
    state: Literal["draft", "pending_review", "approved", "rejected", "archived"]
    source_type: Literal["best_run", "ipynb_import"]
    source_evidence: list[str]
    artifacts: list[dict[str, str]] = Field(default_factory=list)
    requirements: dict[str, Any] = Field(default_factory=dict)
    human_review: HumanReview
    performance: dict[str, Any]
    reproducibility: dict[str, Any]
    valid_from: str | None = None
    superseded_by: str | None = None

    @model_validator(mode="after")
    def approved_requires_review(self) -> "SkillVersion":
        if self.state == "approved" and not self.human_review.reviewed:
            raise ValueError("approved SkillVersion requires human_review.reviewed=true")
        return self


class ContextPack(BaseModel):
    pack_type: Literal["exploration", "retraining", "distillation", "skill_candidate"]
    prompt: str
    sections: list[dict[str, Any]]


class PrimaryMetric(BaseModel):
    name: str = Field(min_length=1)
    value: float

    @field_validator("value")
    @classmethod
    def _value_must_be_finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("metric value must be finite (not NaN or inf)")
        return v


class BenchmarkMetric(BaseModel):
    name: str = Field(min_length=1)
    value: float

    @field_validator("value")
    @classmethod
    def _value_must_be_finite(cls, v: float) -> float:
        if not math.isfinite(v):
            raise ValueError("metric value must be finite (not NaN or inf)")
        return v


class Performance(BaseModel):
    primary_metric: PrimaryMetric
    dataset_version: str = Field(min_length=1)
    validation_protocol: str = Field(min_length=1)
    benchmark_metric: BenchmarkMetric | None = None
    target_or_acceptance_note: str | None = None
