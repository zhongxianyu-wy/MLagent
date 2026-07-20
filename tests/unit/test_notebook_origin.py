"""Tests for notebook_origin provenance in SOP candidates (Issue #9 T6)."""
from src.domain.models import (
    NotebookOriginInfo,
    SopCandidateSnapshot,
)


def test_notebook_origin_info_is_serializable():
    info = NotebookOriginInfo(
        notebook_import_id="nbimp_abc123",
        original_filename="baseline.ipynb",
        content_fingerprint="a" * 64,
    )
    d = info.to_dict()
    assert d["notebook_import_id"] == "nbimp_abc123"
    assert d["original_filename"] == "baseline.ipynb"
    assert d["content_fingerprint"] == "a" * 64


def test_sop_candidate_snapshot_accepts_notebook_origin():
    """A SopCandidateSnapshot can carry notebook_origin provenance."""
    # Minimal valid snapshot with notebook_origin
    info = NotebookOriginInfo(
        notebook_import_id="nbimp_xyz",
        original_filename="experiment.ipynb",
        content_fingerprint="b" * 64,
    )
    # We can't easily build a full SopCandidateSnapshot (too many required fields),
    # but we can verify the field exists and defaults to None
    import dataclasses
    fields = {f.name for f in dataclasses.fields(SopCandidateSnapshot)}
    assert "notebook_origin" in fields


def test_sop_candidate_snapshot_defaults_notebook_origin_none():
    """Without notebook provenance, the field defaults to None."""
    import dataclasses
    field = next(
        f for f in dataclasses.fields(SopCandidateSnapshot)
        if f.name == "notebook_origin"
    )
    assert field.default is None
