"""Span of Control analytics.

Span of control = number of *active* direct reports. A manager is any active
employee with at least one active direct report.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from utils.config import Settings
from utils.helpers import blank_to_label

SPAN_LOW = "Low"
SPAN_HIGH = "High"
SPAN_OK = "Within Range"


def span_category(n: int, settings: Settings) -> str:
    if n <= settings.low_span_threshold:
        return SPAN_LOW
    if n > settings.high_span_threshold:
        return SPAN_HIGH
    return SPAN_OK


def manager_table(df: pd.DataFrame, settings: Settings) -> pd.DataFrame:
    """One row per manager with span metrics and category."""
    m = df[df["is_manager"]].copy()
    cols = ["node_id", "employee_name", "job_title", "job_level", "department", "division",
            "business_unit", "location", "depth", "direct_reports", "vacant_direct_positions",
            "total_reports", "salary"]
    m = m[cols]
    m["span_category"] = m["direct_reports"].map(lambda n: span_category(int(n), settings))
    return m.sort_values("direct_reports", ascending=False).reset_index(drop=True)


def span_stats(spans: pd.Series) -> dict:
    s = pd.Series(spans, dtype=float).dropna()
    if s.empty:
        return {k: np.nan for k in ("min", "max", "mean", "median", "p25", "p75")} | {"count": 0}
    return {
        "count": int(s.size),
        "min": float(s.min()),
        "max": float(s.max()),
        "mean": float(s.mean()),
        "median": float(s.median()),
        "p25": float(s.quantile(0.25)),
        "p75": float(s.quantile(0.75)),
    }


def span_distribution(df: pd.DataFrame) -> pd.DataFrame:
    s = df.loc[df["is_manager"], "direct_reports"]
    return s.value_counts().sort_index().rename_axis("direct_reports").reset_index(name="managers")


def span_by(df: pd.DataFrame, by: str, settings: Settings) -> pd.DataFrame:
    """Span statistics grouped by a column (department, job_level, ...)."""
    m = df[df["is_manager"]]
    if m.empty:
        return pd.DataFrame(columns=[by, "managers", "avg_span", "median_span", "min_span",
                                     "max_span", "low_span_managers", "high_span_managers"])
    key = blank_to_label(m[by])
    g = m.groupby(key)["direct_reports"]
    out = pd.DataFrame({
        "managers": g.size(),
        "avg_span": g.mean().round(2),
        "median_span": g.median(),
        "min_span": g.min(),
        "max_span": g.max(),
        "low_span_managers": g.apply(lambda s: int((s <= settings.low_span_threshold).sum())),
        "high_span_managers": g.apply(lambda s: int((s > settings.high_span_threshold).sum())),
    })
    return out.rename_axis(by).reset_index()
