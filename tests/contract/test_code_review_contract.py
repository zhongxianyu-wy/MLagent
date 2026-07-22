"""Contract tests for the Code Review UI module (Issue #11 T6).

These guard the §3.14 boundary: the UI must not read or write managed code
files directly — every read/write goes through DomainCore. They also pin the
module-status vocabulary so the shell never surfaces an unlisted status.
"""
from __future__ import annotations

import re
from pathlib import Path

from src.ui import shell as shell_module

APP_PATH = Path(__file__).resolve().parents[2] / "src" / "ui" / "app.py"


def _render_code_review_source() -> str:
    source = APP_PATH.read_text(encoding="utf-8")
    match = re.search(
        r"def _render_code_review\(.*?(?=\ndef )",
        source,
        re.DOTALL,
    )
    assert match, "_render_code_review function not found in src/ui/app.py"
    return match.group(0)


def test_workspace_changed_belongs_to_global_vocabulary():
    assert "Workspace changed" in shell_module.GLOBAL_STATUS_VOCABULARY


def test_code_review_statuses_assigned_by_ui_are_in_vocabulary():
    allowed = set(shell_module.GLOBAL_STATUS_VOCABULARY)
    # the only statuses app.py computes for the Code Review module
    for status in ("Workspace changed", "Approved", "Pending confirmation"):
        assert status in allowed, f"{status!r} is not in GLOBAL_STATUS_VOCABULARY"


def test_ui_reads_managed_code_only_through_domain_core():
    body = _render_code_review_source()
    # no direct filesystem reads of code inside the UI module
    assert "read_bytes()" not in body
    assert ".read_text(" not in body
    assert re.search(r"\bopen\(", body) is None
    # reads are routed through the domain core
    assert "core.read_managed_file" in body


def test_ui_writes_code_revisions_only_through_domain_core():
    body = _render_code_review_source()
    # no direct filesystem writes
    assert ".write_bytes(" not in body
    assert ".write_text(" not in body
    # writes are routed through the domain core via the command object
    assert "core.save_code_revision" in body
    assert "SaveCodeRevisionCommand" in body


def test_code_review_dispatch_branch_exists():
    source = APP_PATH.read_text(encoding="utf-8")
    assert 'selected_module == "Code Review"' in source
    assert "_render_code_review" in source
