"""Data Quality engine: Completeness, Uniqueness, Validity, Consistency and
Referential Integrity checks. Every check returns the exact affected records."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import pandas as pd

from analytics.hierarchy import OrgModel
from utils.config import (
    EMPLOYMENT_STATUSES,
    EMPLOYMENT_TYPES,
    POSITION_STATUSES,
    RS_CIRCULAR,
    RS_INVALID,
    RS_TERMINATED,
    WORK_ARRANGEMENTS,
)


@dataclass
class Check:
    check_id: str
    dimension: str
    name: str
    field: str
    description: str
    scope: Callable[[pd.DataFrame, OrgModel], pd.Series]  # rows the check applies to
    fails: Callable[[pd.DataFrame, OrgModel], pd.Series]  # rows that fail (within scope)


def _filled(df, m):
    return ~df["is_vacant"]


def _all(df, m):
    return pd.Series(True, index=df.index)


def _positions(df, m):
    return ~df["is_duplicate_id"]


def _active(df, m):
    return df["is_active"]


def _non_ceo_filled(df, m):
    return ~df["is_vacant"] & df["node_id"].ne(m.ceo_id) & df["employment_status"].ne("Terminated")


def _blank(col):
    return lambda df, m: df[col].astype(str).str.strip().isin(["", "nan", "NaT", "<NA>", "None"]) \
        | df[col].isna()


def _manager_level_inverted(df, m):
    lvl = dict(zip(df["node_id"], df["job_level"]))
    mgr_lvl = df["manager_id"].map(lvl)
    return mgr_lvl.notna() & df["job_level"].notna() & (mgr_lvl > df["job_level"])


def _dept_multi_division(df, m):
    d = df[df["department"].ne("") & df["division"].ne("")]
    n = d.groupby("department")["division"].nunique()
    bad = set(n[n > 1].index)
    return df["department"].isin(bad)


def _manager_name_mismatch(df, m):
    names = dict(zip(df["node_id"], df["employee_name"]))
    actual = df["manager_id"].map(names)
    recorded = df["manager_name"]
    return actual.notna() & recorded.ne("") & actual.ne("") & recorded.ne("(Vacant)") \
        & actual.str.lower().ne(recorded.str.lower())


def _salary_band_outlier(df, m):
    """Salary outside the 1.5*IQR fences of its job level."""
    s = df["salary"]
    out = pd.Series(False, index=df.index)
    for lvl, grp in df[s.notna() & df["job_level"].notna()].groupby("job_level"):
        q1, q3 = grp["salary"].quantile([0.25, 0.75])
        iqr = q3 - q1
        lo, hi = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        out.loc[grp.index] = (grp["salary"] < lo) | (grp["salary"] > hi)
    return out


CHECKS: list[Check] = [
    # ------------------------------------------------------------------ completeness
    Check("C01", "Completeness", "Employee ID Completeness", "employee_id",
          "Employee ID populated for filled positions", _filled, _blank("employee_id")),
    Check("C02", "Completeness", "Employee Name Completeness", "employee_name",
          "Name populated for filled positions", _filled, _blank("employee_name")),
    Check("C03", "Completeness", "Manager ID Completeness", "manager_id",
          "Manager ID populated for everyone except the CEO", _non_ceo_filled, _blank("manager_id")),
    Check("C04", "Completeness", "Job Title Completeness", "job_title",
          "Job title populated", _positions, _blank("job_title")),
    Check("C05", "Completeness", "Department Completeness", "department",
          "Department populated", _positions, _blank("department")),
    Check("C06", "Completeness", "Division Completeness", "division",
          "Division populated", _positions, _blank("division")),
    Check("C07", "Completeness", "Business Unit Completeness", "business_unit",
          "Business unit populated", _positions, _blank("business_unit")),
    Check("C08", "Completeness", "Job Level Completeness", "job_level",
          "Job level populated", _positions, lambda df, m: df["job_level"].isna()),
    Check("C09", "Completeness", "Salary Completeness", "salary",
          "Salary populated for filled positions", _filled, lambda df, m: df["salary"].isna()),
    Check("C10", "Completeness", "Position ID Completeness", "position_id",
          "Position ID populated", _all, _blank("position_id")),
    Check("C11", "Completeness", "Hire Date Completeness", "hire_date",
          "Hire date populated for filled positions", _filled, lambda df, m: df["hire_date"].isna()),
    # ------------------------------------------------------------------ uniqueness
    Check("U01", "Uniqueness", "Employee ID Uniqueness", "employee_id",
          "Each Employee ID appears once",
          lambda df, m: ~df["is_vacant"] & df["employee_id"].ne(""),
          lambda df, m: df["employee_id"].ne("") & df["employee_id"].duplicated(keep=False)),
    Check("U02", "Uniqueness", "Position ID Uniqueness", "position_id",
          "Each Position ID appears once", lambda df, m: df["position_id"].ne(""),
          lambda df, m: df["position_id"].ne("") & df["position_id"].duplicated(keep=False)),
    # ------------------------------------------------------------------ validity
    Check("V01", "Validity", "Salary Validity", "salary", "Salary is a positive number",
          lambda df, m: ~df["is_vacant"] & df["salary"].notna(),
          lambda df, m: df["salary"] <= 0),
    Check("V02", "Validity", "Job Level Validity", "job_level", "Job level is an integer 0-6",
          lambda df, m: df["job_level"].notna(),
          lambda df, m: ~df["job_level"].between(0, 6) | (df["job_level"] % 1 != 0)),
    Check("V03", "Validity", "Employment Status Validity", "employment_status",
          f"One of {', '.join(EMPLOYMENT_STATUSES)}", _filled,
          lambda df, m: ~df["employment_status"].isin(EMPLOYMENT_STATUSES)),
    Check("V04", "Validity", "Position Status Validity", "position_status",
          f"One of {', '.join(POSITION_STATUSES)}", _all,
          lambda df, m: ~df["position_status"].isin(POSITION_STATUSES)),
    Check("V05", "Validity", "Employment Type Validity", "employment_type",
          f"One of {', '.join(EMPLOYMENT_TYPES)}",
          lambda df, m: ~df["is_vacant"] & df["employment_type"].ne(""),
          lambda df, m: ~df["employment_type"].isin(EMPLOYMENT_TYPES)),
    Check("V06", "Validity", "Work Arrangement Validity", "work_arrangement",
          f"One of {', '.join(WORK_ARRANGEMENTS)}",
          lambda df, m: ~df["is_vacant"] & df["work_arrangement"].ne(""),
          lambda df, m: ~df["work_arrangement"].isin(WORK_ARRANGEMENTS)),
    Check("V07", "Validity", "Age Validity", "age", "Age between 16 and 80",
          lambda df, m: df["age"].notna(), lambda df, m: ~df["age"].between(16, 80)),
    Check("V08", "Validity", "Hire Date Validity", "hire_date", "Hire date is not in the future",
          lambda df, m: df["hire_date"].notna(),
          lambda df, m: df["hire_date"] > pd.Timestamp.today().normalize()),
    Check("V09", "Validity", "Performance Rating Validity", "performance_rating",
          "Rating between 1 and 5", lambda df, m: df["performance_rating"].notna(),
          lambda df, m: ~df["performance_rating"].between(1, 5)),
    # ------------------------------------------------------------------ consistency
    Check("S01", "Consistency", "Terminated Employee / Position Status", "position_status",
          "Terminated employees should not hold a 'Filled' position",
          lambda df, m: df["employment_status"].eq("Terminated"),
          lambda df, m: df["position_status"].eq("Filled")),
    Check("S02", "Consistency", "Manager Job Level Seniority", "job_level",
          "Manager's job level is equal or more senior than the employee's",
          lambda df, m: df["is_active"] & df["manager_id"].ne(""), _manager_level_inverted),
    Check("S03", "Consistency", "Manager-level Role Without Reports", "job_level",
          "Job levels 0-5 are expected to have at least one active direct report",
          lambda df, m: df["is_active"] & df["job_level"].le(5),
          lambda df, m: df["direct_reports"].eq(0)),
    Check("S04", "Consistency", "Department → Division Mapping", "division",
          "Each department belongs to exactly one division", _positions, _dept_multi_division),
    Check("S05", "Consistency", "Manager Name Matches Manager ID", "manager_name",
          "Recorded manager name matches the manager's record",
          lambda df, m: df["manager_id"].ne("") & df["manager_name"].ne(""),
          _manager_name_mismatch),
    Check("S06", "Consistency", "Vacant Position Without Employee Data", "employee_name",
          "Vacant positions carry no employee name",
          lambda df, m: df["is_vacant"], lambda df, m: df["employee_name"].ne("")),
    Check("S07", "Consistency", "Salary Within Job Level Band", "salary",
          "Salary within 1.5×IQR of its job level",
          lambda df, m: df["is_active"] & df["salary"].notna(), _salary_band_outlier),
    # ------------------------------------------------------------------ referential integrity
    Check("R01", "Referential Integrity", "Manager Reference Validity", "manager_id",
          "Manager ID refers to an existing record",
          lambda df, m: df["manager_id"].ne("") & (df["is_active"] | df["is_vacant"]),
          lambda df, m: df["reporting_status"].eq(RS_INVALID)),
    Check("R02", "Referential Integrity", "Manager Is Active", "manager_id",
          "Manager record is Active / On Leave (or a vacant position)",
          lambda df, m: df["is_active"] & df["manager_id"].ne(""),
          lambda df, m: df["reporting_status"].eq(RS_TERMINATED)),
    Check("R03", "Referential Integrity", "No Circular Reporting", "manager_id",
          "Reporting chain does not loop", _active,
          lambda df, m: df["reporting_status"].eq(RS_CIRCULAR)),
    Check("R04", "Referential Integrity", "Reaches the CEO", "manager_id",
          "Reporting chain reaches the top of the hierarchy", _active,
          lambda df, m: df["depth"].isna()),
    Check("R05", "Referential Integrity", "Single Top of Hierarchy", "manager_id",
          "Only one active employee without a manager", lambda df, m: df["is_active"] & df["manager_id"].eq(""),
          lambda df, m: df["node_id"].ne(m.ceo_id)),
]


def run_checks(model: OrgModel, df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Run all checks. Returns one row per check with score and failing node IDs."""
    data = df if df is not None else model.df
    rows = []
    for c in CHECKS:
        try:
            scope = c.scope(data, model).fillna(False).astype(bool)
            fails = c.fails(data, model).fillna(False).astype(bool) & scope
            n_scope, n_fail = int(scope.sum()), int(fails.sum())
            error = ""
        except Exception as exc:  # pragma: no cover - defensive
            n_scope, n_fail, fails, error = 0, 0, pd.Series(False, index=data.index), str(exc)
        score = 1.0 if n_scope == 0 else (n_scope - n_fail) / n_scope
        rows.append({
            "check_id": c.check_id, "dimension": c.dimension, "check": c.name,
            "field": c.field, "rule": c.description, "records_checked": n_scope,
            "failed": n_fail, "score": score,
            "status": "Pass" if n_fail == 0 else ("Warning" if score >= 0.98 else "Fail"),
            "failing_rows": data.index[fails].tolist(), "error": error,
        })
    return pd.DataFrame(rows)


def dimension_scores(checks: pd.DataFrame) -> pd.DataFrame:
    """Average score per dimension (weighted by records checked)."""
    if checks.empty:
        return pd.DataFrame(columns=["dimension", "score", "failed"])
    g = checks.assign(passed=checks["records_checked"] - checks["failed"]).groupby("dimension")
    out = pd.DataFrame({"records": g["records_checked"].sum(), "passed": g["passed"].sum(),
                        "failed": g["failed"].sum()})
    out["score"] = out["passed"] / out["records"].where(out["records"] > 0)
    return out.reset_index()[["dimension", "score", "failed", "records"]]


def overall_score(checks: pd.DataFrame) -> float:
    tot = checks["records_checked"].sum()
    return float((tot - checks["failed"].sum()) / tot) if tot else 1.0


def affected_records(model: OrgModel, checks: pd.DataFrame, check_id: str,
                     df: pd.DataFrame | None = None) -> pd.DataFrame:
    data = df if df is not None else model.df
    row = checks[checks["check_id"].eq(check_id)]
    if row.empty:
        return data.iloc[0:0]
    return data.loc[row.iloc[0]["failing_rows"]]

