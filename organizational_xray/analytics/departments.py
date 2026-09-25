"""Organisational-unit analytics: departments / divisions / business units,
organisational layers and job-title analysis."""
from __future__ import annotations

import re
from difflib import SequenceMatcher
from itertools import combinations

import numpy as np
import pandas as pd

from utils.config import INVALID_REPORTING_STATUSES, LEVEL_NAMES, Settings
from utils.helpers import blank_to_label, safe_div

UNIT_COLUMNS = [
    "headcount", "managers", "management_ratio", "avg_span", "avg_depth", "max_depth",
    "layers", "vacancies", "positions", "vacancy_rate", "avg_salary", "median_salary",
    "invalid_reporting",
]


def unit_metrics(df: pd.DataFrame, by: str = "department", settings: Settings | None = None
                 ) -> pd.DataFrame:
    """Metrics per organisational unit (``by`` = department / division / business_unit).

    * headcount         active employees (Active + On Leave)
    * managers          active employees with >= 1 active direct report
    * management_ratio  managers / headcount
    * avg_span          mean direct reports of the unit's managers
    * avg_depth         mean distance to the CEO of the unit's employees
    * layers            number of distinct depth levels present in the unit
    * vacancies         positions with Position Status = Vacant
    * vacancy_rate      vacancies / (vacancies + filled positions of active employees)
    """
    settings = settings or Settings()
    d = df.assign(_unit=blank_to_label(df[by]))
    act = d[d["is_active"]]
    vac = d[d["is_vacant"] & ~d["is_duplicate_id"]]
    units = sorted(set(act["_unit"]) | set(vac["_unit"]))
    if not units:
        return pd.DataFrame(columns=[by] + UNIT_COLUMNS)

    ga = act.groupby("_unit")
    mgr = act[act["is_manager"]].groupby("_unit")["direct_reports"]
    out = pd.DataFrame(index=pd.Index(units, name=by))
    out["headcount"] = ga.size()
    out["managers"] = act.groupby("_unit")["is_manager"].sum()
    out = out.fillna({"headcount": 0, "managers": 0}).astype({"headcount": int, "managers": int})
    out["management_ratio"] = [safe_div(m, h) for m, h in zip(out["managers"], out["headcount"])]
    out["avg_span"] = mgr.mean().round(2)
    out["median_span"] = mgr.median()
    out["avg_depth"] = ga["depth"].mean().round(2)
    out["max_depth"] = ga["depth"].max()
    out["layers"] = ga["depth"].nunique()
    out["vacancies"] = vac.groupby("_unit").size()
    out["vacancies"] = out["vacancies"].fillna(0).astype(int)
    out["positions"] = out["headcount"] + out["vacancies"]
    out["vacancy_rate"] = [safe_div(v, p) for v, p in zip(out["vacancies"], out["positions"])]
    out["avg_salary"] = ga["salary"].mean().round(0)
    out["median_salary"] = ga["salary"].median()
    out["invalid_reporting"] = act.groupby("_unit")["reporting_status"].apply(
        lambda s: int(s.isin(INVALID_REPORTING_STATUSES).sum()))
    out["invalid_reporting"] = out["invalid_reporting"].fillna(0).astype(int)
    out["layers"] = out["layers"].fillna(0).astype(int)
    out["low_span_managers"] = mgr.apply(lambda s: int((s <= settings.low_span_threshold).sum()))
    out["high_span_managers"] = mgr.apply(lambda s: int((s > settings.high_span_threshold).sum()))
    out[["low_span_managers", "high_span_managers"]] = (
        out[["low_span_managers", "high_span_managers"]].fillna(0).astype(int))
    if by == "department":
        parents = d.groupby("_unit")[["division", "business_unit"]].agg(
            lambda s: s.mode().iloc[0] if not s.mode().empty else "")
        out = out.join(parents)
    return out.reset_index().sort_values("headcount", ascending=False).reset_index(drop=True)


def layer_metrics(df: pd.DataFrame, basis: str = "job_level") -> pd.DataFrame:
    """Per-layer summary. ``basis`` = 'job_level' (declared) or 'depth' (measured)."""
    act = df[df["is_active"]]
    total = len(act)
    key = act[basis]
    rows = []
    for layer, grp in act.groupby(key.fillna(-1).astype(int)):
        mg = grp[grp["is_manager"]]
        if basis == "job_level":
            name = LEVEL_NAMES.get(layer, "Unknown") if layer >= 0 else "Unknown level"
        else:
            name = f"Layer {layer}" if layer >= 0 else "Unreachable"
        rows.append({
            "layer": layer if layer >= 0 else None,
            "layer_name": name,
            "employees": len(grp),
            "pct_of_total": safe_div(len(grp), total),
            "managers": len(mg),
            "avg_salary": grp["salary"].mean(),
            "avg_span": mg["direct_reports"].mean() if len(mg) else np.nan,
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return pd.DataFrame(columns=["layer", "layer_name", "employees", "pct_of_total",
                                     "managers", "avg_salary", "avg_span"])
    return out.sort_values("layer", na_position="last").reset_index(drop=True)


# ============================================================================ job titles
_SENIORITY = {"senior", "sr", "junior", "jr", "staff", "lead", "principal", "chief", "head",
              "assistant", "associate", "i", "ii", "iii"}
_STOP = {"&", "and", "of", "the", "-", ","}


def normalize_title(title: str) -> str:
    t = re.sub(r"[^\w&/ ]+", " ", str(title).lower())
    return re.sub(r"\s+", " ", t).strip()


def _core(title_norm: str) -> str:
    return " ".join(w for w in title_norm.split() if w not in _SENIORITY)


def _acronym_form(title_norm: str) -> str:
    """'learning & development specialist' -> 'ld specialist'; 'l&d specialist' -> same."""
    words = [w for w in title_norm.split() if w not in _STOP]
    if len(words) < 2:
        return title_norm
    head = "".join(w.replace("&", "") if "&" in w else w[0] for w in words[:-1])
    return f"{head} {words[-1]}"


def title_similarity(a: str, b: str) -> float:
    """Similarity (0-1) of two job titles.

    Character similarity alone over-matches ("Brand Specialist" ~ "HR Specialist"),
    so a pair only scores when the titles are structurally related:
      * acronym variants ("L&D Specialist" ~ "Learning & Development Specialist") -> 0.95
      * one title's words are contained in the other's ("HR Analyst" ~ "HR Data Analyst")
      * exactly one word differs and those words are themselves alike ("HR" ~ "HRIS")
    Otherwise the score is 0.
    """
    na, nb = normalize_title(a), normalize_title(b)
    if na == nb:
        return 1.0
    if _acronym_form(na) == _acronym_form(nb) and len(na.split()) != len(nb.split()):
        return 0.95
    ta = [w for w in na.split() if w not in _STOP]
    tb = [w for w in nb.split() if w not in _STOP]
    sa, sb = set(ta), set(tb)
    ratio = SequenceMatcher(None, na, nb).ratio()
    if sa < sb or sb < sa:
        return ratio
    da, db = sa - sb, sb - sa
    if len(da) == 1 and len(db) == 1 and len(ta) == len(tb):
        wa, wb = next(iter(da)), next(iter(db))
        if SequenceMatcher(None, wa, wb).ratio() >= 0.5:
            return ratio
    return 0.0


def job_title_analysis(df: pd.DataFrame, settings: Settings | None = None) -> dict:
    """Duplicate titles, raw variants of the same title, and similar-title pairs.

    Similar titles are compared within the same division (overlapping roles
    inside one function are the ones worth reviewing).
    """
    settings = settings or Settings()
    rows = df[(df["is_active"] | df["is_vacant"]) & df["job_title"].ne("")]
    counts = (rows.groupby("job_title")
              .agg(positions=("node_id", "size"),
                   departments=("department", lambda s: ", ".join(sorted(set(s) - {""}))),
                   n_departments=("department", lambda s: len(set(s) - {""})))
              .reset_index().sort_values("positions", ascending=False))
    counts["normalized"] = counts["job_title"].map(normalize_title)

    # Titles that are identical after normalisation but typed differently
    variants = []
    for norm, grp in counts.groupby("normalized"):
        if len(grp) > 1:
            variants.append({"normalized_title": norm,
                             "variants": " | ".join(grp["job_title"]),
                             "positions": int(grp["positions"].sum()),
                             "departments": ", ".join(sorted(set(", ".join(grp["departments"])
                                                                 .split(", ")) - {""}))})
    variants_df = pd.DataFrame(variants, columns=["normalized_title", "variants", "positions",
                                                  "departments"])

    # Similar (not identical) titles, within each division
    norms = dict(zip(counts["job_title"], counts["normalized"]))
    pos = dict(zip(counts["job_title"], counts["positions"]))
    depts = dict(zip(counts["job_title"], counts["departments"]))
    thr = settings.title_similarity_threshold
    seen: set[tuple[str, str]] = set()
    pairs = []
    for division, grp in rows.groupby(blank_to_label(rows["division"])):
        titles = list(dict.fromkeys(t for t in grp["job_title"]))
        titles = sorted({norms[t]: t for t in titles}.values())[:1500]
        for a, b in combinations(titles, 2):
            key = tuple(sorted((a, b)))
            if key in seen:
                continue
            na, nb = norms[a], norms[b]
            if _core(na) == _core(nb):
                continue  # same job family, different seniority: a career ladder
            score = title_similarity(a, b)
            if score >= thr:
                seen.add(key)
                pairs.append({"title_a": a, "title_b": b, "similarity": round(score, 3),
                              "division": division,
                              "positions_a": pos[a], "positions_b": pos[b],
                              "departments_a": depts[a], "departments_b": depts[b]})
    similar_df = pd.DataFrame(pairs, columns=["title_a", "title_b", "similarity", "division",
                                              "positions_a", "positions_b", "departments_a",
                                              "departments_b"])
    similar_df = similar_df.sort_values("similarity", ascending=False).reset_index(drop=True)
    return {"titles": counts.reset_index(drop=True), "variants": variants_df,
            "similar": similar_df}


def duplicate_position_ids(df: pd.DataFrame) -> pd.DataFrame:
    d = df[df["position_id"].ne("") & ~df["is_duplicate_id"]]
    dup = d[d["position_id"].duplicated(keep=False)]
    return dup.sort_values("position_id")
