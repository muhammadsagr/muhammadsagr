"""Organizational X-Ray - entry point.

Run with:  streamlit run app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import streamlit as st  # noqa: E402

from ui import (  # noqa: E402
    dashboard,
    data_quality,
    departments,
    explorer,
    export_page,
    findings,
    import_data,
    layers,
    network_page,
    settings_page,
    simulator,
    span,
)
from ui.common import inject_css, sidebar_filters  # noqa: E402
from ui.state import cached_model, init_state  # noqa: E402

st.set_page_config(page_title="Organizational X-Ray", page_icon="🩻", layout="wide")
inject_css()
init_state()

PAGES = [
    st.Page(dashboard.render, title="Dashboard", icon=":material/monitor_heart:",
            url_path="dashboard", default=True),
    st.Page(layers.render, title="Layers", icon=":material/layers:", url_path="layers"),
    st.Page(span.render, title="Span of Control", icon=":material/account_tree:", url_path="span"),
    st.Page(departments.render, title="Departments", icon=":material/apartment:",
            url_path="departments"),
    st.Page(network_page.render, title="Organization Map", icon=":material/hub:",
            url_path="organization-map"),
    st.Page(explorer.render, title="Employee Explorer", icon=":material/person_search:",
            url_path="explorer"),
    st.Page(findings.render, title="X-Ray Findings", icon=":material/radiology:",
            url_path="findings"),
    st.Page(data_quality.render, title="Data Quality", icon=":material/fact_check:",
            url_path="data-quality"),
    st.Page(simulator.render, title="What-If Simulator", icon=":material/science:",
            url_path="simulator"),
    st.Page(import_data.render, title="Import Data", icon=":material/upload_file:",
            url_path="import"),
    st.Page(export_page.render, title="Export", icon=":material/download:", url_path="export"),
    st.Page(settings_page.render, title="Settings", icon=":material/tune:", url_path="settings"),
]

nav = st.navigation({"Organizational X-Ray": PAGES})
ds = st.session_state.dataset
sidebar_filters(cached_model(ds["token"], ds["raw"]))
nav.run()
