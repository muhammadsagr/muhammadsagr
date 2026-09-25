"""Session state, caching and the per-run analysis context.

Heavy work is cached by a *dataset token* (and the settings for rule-based
results), so filter changes and page switches never rebuild the hierarchy.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import streamlit as st

from analytics.anomalies import detect_findings, filter_findings
from analytics.data_quality import run_checks
from analytics.hierarchy import OrgModel, build_org_model
from data.dummy_generator import generate_org
from data.loader import normalize
from utils.config import Settings
from utils.helpers import df_fingerprint

FILTERS = [
    ("business_unit", "Business Unit"),
    ("division", "Division"),
    ("department", "Department"),
    ("location", "Location"),
    ("job_level", "Job Level"),
    ("employment_status", "Employment Status"),
    ("employment_type", "Employment Type"),
]


# ============================================================================ cached work
@st.cache_data(show_spinner="Generating dummy organisation…", max_entries=4)
def cached_dummy(n: int, seed: int) -> tuple[pd.DataFrame, list[dict]]:
    return generate_org(n, seed)


@st.cache_resource(show_spinner="Building organisational hierarchy…", max_entries=4)
def cached_model(token: str, _raw: pd.DataFrame) -> OrgModel:
    return build_org_model(normalize(_raw))


@st.cache_data(show_spinner="Running X-Ray rules…", max_entries=16)
def cached_findings(token: str, settings_key: tuple, _model: OrgModel) -> pd.DataFrame:
    return detect_findings(_model, Settings(*settings_key))


@st.cache_data(show_spinner="Checking data quality…", max_entries=8)
def cached_quality(token: str, _model: OrgModel) -> pd.DataFrame:
    return run_checks(_model)


# ============================================================================ session
def init_state() -> None:
    ss = st.session_state
    if "settings" not in ss:
        ss.settings = Settings()
    if "dataset" not in ss:
        load_dummy(1500, 42)
    ss.setdefault("scenario", [])


def load_dummy(n: int, seed: int) -> None:
    raw, manifest = cached_dummy(n, seed)
    st.session_state.dataset = {
        "raw": raw, "token": f"dummy-{n}-{seed}", "manifest": manifest,
        "source": f"Dummy data · ~{n:,} employees · seed {seed}",
    }
    reset_filters()
    st.session_state.scenario = []


def load_uploaded(raw: pd.DataFrame, filename: str) -> None:
    st.session_state.dataset = {
        "raw": raw, "token": f"upload-{df_fingerprint(raw)}", "manifest": None,
        "source": f"Uploaded file · {filename} · {len(raw):,} rows",
    }
    reset_filters()
    st.session_state.scenario = []


def reset_filters() -> None:
    for key, _ in FILTERS:
        st.session_state[f"flt_{key}"] = []
    st.session_state["flt_manager"] = None


# ============================================================================ context
@dataclass
class Context:
    raw: pd.DataFrame
    token: str
    source: str
    manifest: list | None
    model: OrgModel
    settings: Settings
    findings_all: pd.DataFrame
    df: pd.DataFrame  # filtered enriched records
    findings: pd.DataFrame  # findings touching the filtered records
    filtered: bool
    filter_summary: str

    @property
    def active(self) -> pd.DataFrame:
        return self.df[self.df["is_active"]]


def _filter_mask(model: OrgModel) -> tuple[pd.Series, list[str]]:
    df = model.df
    mask = pd.Series(True, index=df.index)
    parts = []
    for key, label in FILTERS:
        sel = st.session_state.get(f"flt_{key}") or []
        if sel:
            col = df[key]
            if key == "job_level":
                mask &= col.isin([float(s) for s in sel])
            else:
                mask &= col.isin(sel)
            parts.append(f"{label}: {', '.join(map(str, sel[:3]))}{'…' if len(sel) > 3 else ''}")
    mgr = st.session_state.get("flt_manager")
    if mgr:
        ids = set(model.subtree_ids(mgr, include_root=True, include_vacant=True))
        mask &= df["node_id"].isin(ids)
        parts.append(f"Manager: {mgr}")
    return mask, parts


def context() -> Context:
    ss = st.session_state
    ds = ss.dataset
    settings: Settings = ss.settings
    model = cached_model(ds["token"], ds["raw"])
    findings_all = cached_findings(ds["token"], settings.cache_key(), model)
    mask, parts = _filter_mask(model)
    filtered = bool(parts)
    df = model.df[mask] if filtered else model.df
    findings = findings_all
    if filtered:
        findings = filter_findings(findings_all, set(df["node_id"]),
                                   set(df["department"]))
    return Context(raw=ds["raw"], token=ds["token"], source=ds["source"],
                   manifest=ds.get("manifest"), model=model, settings=settings,
                   findings_all=findings_all, df=df, findings=findings, filtered=filtered,
                   filter_summary=" · ".join(parts))


def filter_options(model: OrgModel) -> dict[str, list]:
    df = model.df[~model.df["is_duplicate_id"]]
    opts = {}
    for key, _ in FILTERS:
        vals = df[key].dropna()
        if key == "job_level":
            opts[key] = sorted({int(v) for v in vals})
        else:
            opts[key] = sorted(v for v in set(vals) if v != "")
    return opts
