from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import streamlit as st

# Streamlit executes this file as a script and otherwise omits the project root.
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.domain.core import DomainCore
from src.domain.models import DatasetVersionSnapshot, WorkspaceError
from src.ui.shell import CONTEXT_LABELS, build_shell_state


def main() -> None:
    st.set_page_config(
        page_title="MLagent",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    _apply_styles()

    connection_path = Path(
        os.environ.get("MLAGENT_WORKSPACE_CONFIG", ".mlagent-workspace.json")
    )
    try:
        core = DomainCore()
        snapshot = core.open_workspace(connection_path)
        dataset = core.get_dataset_overview(connection_path)
    except WorkspaceError as error:
        st.error(error.message)
        st.caption(error.next_action)
        return

    shell = build_shell_state(snapshot, dataset)
    with st.sidebar:
        st.title("MLagent")
        selected_module = st.radio(
            "Workspace modules",
            shell.navigation,
            label_visibility="collapsed",
        )
        st.caption(
            f"Schema {shell.schema_version} · "
            f"{shell.indexed_assets} indexed · {shell.capacity_text}"
        )

    context_columns = st.columns(5)
    for column, (key, value) in zip(context_columns, shell.context.items()):
        with column:
            st.metric(CONTEXT_LABELS[key], value)

    st.divider()
    st.subheader(selected_module)
    st.caption(shell.module_status[selected_module])

    if selected_module == "Dataset Overview":
        _render_dataset_overview(shell.dataset)

    for issue in shell.issues:
        st.warning(f"{issue['message']} {issue['next_action']}")


def _render_dataset_overview(
    dataset: DatasetVersionSnapshot | None,
) -> None:
    if dataset is None:
        st.info("No confirmed Dataset Version")
        return

    summary_columns = st.columns(4)
    summary = (
        ("Version", f"v{dataset.version}"),
        ("Samples", str(dataset.sample_count)),
        ("Features", str(dataset.feature_count)),
        ("Task", dataset.task_type),
    )
    for column, (label, value) in zip(summary_columns, summary):
        with column:
            st.metric(label, value)

    source_names = ", ".join(
        source["name"] for source in dataset.source_files
    )
    evaluation = (
        f"{dataset.primary_metric} · target {dataset.target_metric:g} · "
        f"{dataset.split_strategy} · seed {dataset.random_seed}"
    )
    if dataset.positive_class is not None:
        evaluation += f" · positive {dataset.positive_class}"
    st.caption(evaluation)
    st.caption(source_names)

    preview_rows = [list(row) for row in dataset.preview.rows]
    if dataset.preview.omitted_count:
        omission_row = ["..."] * len(dataset.preview.columns)
        preview_rows.insert(len(preview_rows) // 2, omission_row)
    st.dataframe(
        pd.DataFrame(preview_rows, columns=dataset.preview.columns),
        hide_index=True,
        use_container_width=True,
    )

    field_rows = [
        {
            "Field": field,
            "Type": dataset.dtypes[field],
            "Missing": dataset.missing_rates[field],
        }
        for field in dataset.dtypes
    ]
    st.dataframe(
        pd.DataFrame(field_rows),
        hide_index=True,
        use_container_width=True,
    )
    st.dataframe(
        pd.DataFrame([dataset.class_distribution]),
        hide_index=True,
        use_container_width=True,
    )
    for warning in dataset.warnings:
        st.warning(warning.replace("_", " ").capitalize())


def _apply_styles() -> None:
    st.markdown(
        """
        <style>
        :root {
            --ml-text: #1b2528;
            --ml-muted: #657277;
            --ml-border: #d9e0e2;
            --ml-accent: #147d64;
            --ml-warn: #b66a00;
            --ml-fail: #b83b42;
        }
        html, body, [class*="st-"] {
            letter-spacing: 0;
        }
        [data-testid="stAppViewContainer"] {
            background: #f7f9f8;
            color: var(--ml-text);
        }
        [data-testid="stSidebar"] {
            background: #ffffff;
            border-right: 1px solid var(--ml-border);
        }
        [data-testid="stSidebar"] [role="radiogroup"] label {
            min-height: 42px;
            border-radius: 6px;
        }
        [data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {
            background: #e8f3ef;
            color: #0b5f4c;
        }
        [data-testid="stMetric"] {
            min-height: 76px;
            padding: 4px 0;
            border-bottom: 2px solid var(--ml-border);
        }
        [data-testid="stMetricValue"] {
            font-size: 1rem;
            line-height: 1.3;
            color: var(--ml-text);
        }
        [data-testid="stMetricLabel"] {
            color: var(--ml-muted);
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


main()
