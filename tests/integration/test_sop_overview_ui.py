import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.domain.sop_repository import SopRepository
from tests.integration.test_sop_promotion import (
    DeterministicExecutor,
    make_coordinator,
    review_spec,
)
from tests.integration.test_sop_repository import (
    build_sop_workspace,
    candidate_spec,
)


def test_sop_overview_creates_candidate_from_eligible_instance(
    tmp_path,
    monkeypatch,
):
    workspace = build_sop_workspace(tmp_path)
    connection = write_connection(tmp_path, workspace.root)
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection))

    app = AppTest.from_file(
        Path("src/ui/app.py").resolve(),
        default_timeout=8,
    ).run()
    app = app.sidebar.radio[0].set_value("SOP Overview").run()

    assert not app.exception
    assert app.subheader[0].value == "SOP Overview"
    assert [tab.label for tab in app.tabs] == [
        "Candidates",
        "Approved Versions",
    ]
    assert {item.label for item in app.selectbox} >= {
        "Source Training Instance",
    }
    assert {item.label for item in app.text_input} >= {
        "SOP ID",
        "SOP name",
    }
    assert {item.label for item in app.text_area} >= {
        "Strategy summary",
        "Optimization background",
        "Steps",
        "Change summary",
    }

    app = next(
        item for item in app.text_input if item.label == "SOP ID"
    ).set_value("sop-ui-baseline").run()
    app = next(
        item for item in app.text_input if item.label == "SOP name"
    ).set_value("UI baseline").run()
    app = next(
        item for item in app.text_area if item.label == "Strategy summary"
    ).set_value("Fit the reviewed UI baseline.").run()
    app = next(
        item
        for item in app.text_area
        if item.label == "Optimization background"
    ).set_value("Selected from the current best instance.").run()
    app = next(
        item for item in app.text_area if item.label == "Steps"
    ).set_value("Load frozen data\nExecute frozen code").run()
    app = find_button(app, "Create candidate").click().run()

    assert not app.exception
    candidates = list((workspace.root / "sops/candidates").rglob("manifest.json"))
    assert len(candidates) == 1
    evidence_tables = [
        table.value
        for table in app.dataframe
        if "Role" in table.value.columns
    ]
    assert len(evidence_tables) == 1
    assert len(evidence_tables[0]) == 10
    assert find_button(app, "Run independent reproduction") is not None


def test_sop_overview_displays_approved_version_and_metric_trend(
    tmp_path,
    monkeypatch,
):
    workspace = build_sop_workspace(tmp_path)
    repository = SopRepository(
        workspace.root,
        candidate_id_factory=lambda: "candidate-1",
        gate_id_factory=lambda: "gate-1",
        approval_id_factory=lambda: "sop-approval-1",
        clock=lambda: "2026-07-17T00:10:00Z",
    )
    candidate = repository.create_candidate(
        candidate_spec(workspace),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    gate = make_coordinator(
        workspace,
        repository,
        DeterministicExecutor(),
    )[0].reproduce(candidate)
    repository.review_candidate(
        review_spec(candidate, gate),
        actor_id="alice",
        capacity=workspace.capacity,
    )
    connection = write_connection(tmp_path, workspace.root)
    monkeypatch.setenv("MLAGENT_WORKSPACE_CONFIG", str(connection))

    app = AppTest.from_file(
        Path("src/ui/app.py").resolve(),
        default_timeout=8,
    ).run()
    app = app.sidebar.radio[0].set_value("SOP Overview").run()

    assert not app.exception
    assert [tab.label for tab in app.tabs] == [
        "Candidates",
        "Approved Versions",
    ]
    assert any("sop-random-forest-v0001" in item.value for item in app.markdown)
    assert app.get("arrow_vega_lite_chart") or app.get("vega_lite_chart")
    assert any("instance-reproduction" in item.value for item in app.markdown)
    assert any("Reproduction gate" in item.value for item in app.markdown)
    assert {metric.label for metric in app.metric} >= {
        "Gate source",
        "Gate reproduction",
    }
    environment_tables = [
        table.value
        for table in app.dataframe
        if {"Environment", "Value"}.issubset(table.value.columns)
    ]
    assert len(environment_tables) == 1
    assert set(environment_tables[0]["Environment"]) == {
        "python",
        "sklearn",
    }


def write_connection(tmp_path, repository_path):
    connection = tmp_path / ".mlagent-workspace.json"
    connection.write_text(
        json.dumps(
            {
                "repository_path": str(repository_path),
                "actor_id": "alice",
            }
        ),
        encoding="utf-8",
    )
    return connection


def find_button(app, label):
    return next(button for button in app.button if button.label == label)
