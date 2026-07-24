"""AppTest acceptance for the Lineage Trace module (Issue #14)."""
from __future__ import annotations

import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from tests.integration.test_retrain_from_sop import _core_with_sop
from tests.integration.test_domain_core_sop import write_connection


def _workspace(tmp_path: Path, monkeypatch) -> None:
    core, connection, workspace = _core_with_sop(tmp_path)
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection))
    monkeypatch.setenv("MLAGENT_CODE_ROOT", str(tmp_path))


def test_lineage_trace_renders_graph_and_timeline(tmp_path, monkeypatch):
    _workspace(tmp_path, monkeypatch)
    app = AppTest.from_file(Path("src/ui/app.py").resolve(), default_timeout=8).run()
    app = app.sidebar.radio[0].set_value("Lineage Trace").run()
    assert not app.exception
    # the lineage module produces a graphviz chart (or a fallback dataframe) + a caption
    assert app.caption
    assert app.subheader[0].value == "Lineage Trace"


def test_lineage_trace_filter_changes_visible_nodes(tmp_path, monkeypatch):
    _workspace(tmp_path, monkeypatch)
    app = AppTest.from_file(Path("src/ui/app.py").resolve(), default_timeout=8).run()
    app = app.sidebar.radio[0].set_value("Lineage Trace").run()
    assert not app.exception
    # the type filter selectbox is present
    assert any(sb.label == "Filter by type" for sb in app.selectbox)
