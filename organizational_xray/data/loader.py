"""Reading uploaded files and normalising any dataset to the canonical schema.

``normalize`` never raises on bad *content*: unknown values are kept, missing
columns are created empty, and problems are left for the validator / data
quality engine to report.
"""
from __future__ import annotations

import io
import re
from typing import IO

import numpy as np
import pandas as pd

from utils.config import (
    CANONICAL_COLUMNS,
    DATE_COLUMNS,
    NUMERIC_COLUMNS,
    STRING_COLUMNS,
)

# Header aliases -> canonical name (compared after lower-casing and stripping
# spaces, underscores and dashes).
_ALIASES: dict[str, list[str]] = {
    "employee_id": ["employeeid", "empid", "employeenumber", "empno", "id", "رقمالموظف"],
    "employee_name": ["employeename", "name", "fullname", "الاسم", "اسمالموظف"],
    "gender": ["gender", "sex", "الجنس"],
    "age": ["age", "العمر"],
    "hire_date": ["hiredate", "dateofhire", "joiningdate", "startdate", "تاريخالتوظيف"],
    "employment_status": ["employmentstatus", "status", "employeestatus", "الحالةالوظيفية"],
    "job_title": ["jobtitle", "title", "position", "positiontitle", "المسمىالوظيفي"],
    "job_level": ["joblevel", "level", "layer", "المستوىالوظيفي"],
    "grade": ["grade", "jobgrade", "payGrade".lower(), "الدرجة"],
    "department": ["department", "dept", "الإدارة", "الادارة"],
    "division": ["division", "sector", "القطاع"],
    "business_unit": ["businessunit", "bu", "وحدةالأعمال"],
    "location": ["location", "site", "city", "الموقع"],
    "manager_id": ["managerid", "supervisorid", "reportsto", "linemanagerid", "رقمالمدير"],
    "manager_name": ["managername", "supervisorname", "linemanager", "اسمالمدير"],
    "salary": ["salary", "basesalary", "annualsalary", "الراتب"],
    "position_id": ["positionid", "positionnumber", "posid", "رقمالوظيفة"],
    "position_status": ["positionstatus", "حالةالوظيفة"],
    "employment_type": ["employmenttype", "contracttype", "نوعالتوظيف"],
    "work_arrangement": ["workarrangement", "workmode", "workmodel"],
    "performance_rating": ["performancerating", "rating", "performance", "تقييمالأداء"],
    "years_of_service": ["yearsofservice", "tenure", "yos", "سنواتالخدمة"],
}
_ALIAS_LOOKUP = {a: canon for canon, aliases in _ALIASES.items() for a in aliases}
for _c in CANONICAL_COLUMNS:
    _ALIAS_LOOKUP.setdefault(_c.replace("_", ""), _c)

_STATUS_MAP = {
    "active": "Active", "employed": "Active", "onleave": "On Leave", "leave": "On Leave",
    "loa": "On Leave", "terminated": "Terminated", "inactive": "Terminated",
    "resigned": "Terminated", "exited": "Terminated", "separated": "Terminated",
}
_POSITION_MAP = {"filled": "Filled", "occupied": "Filled", "vacant": "Vacant", "open": "Vacant"}
_TYPE_MAP = {"fulltime": "Full-Time", "parttime": "Part-Time", "contractor": "Contractor",
             "contract": "Contractor", "temporary": "Contractor"}
_WORK_MAP = {"onsite": "On-site", "office": "On-site", "hybrid": "Hybrid", "remote": "Remote"}


def _key(text: str) -> str:
    return re.sub(r"[\s_\-./]+", "", str(text).strip().lower())


def map_columns(columns) -> dict[str, str]:
    """Return {original_header: canonical_name} for recognised headers."""
    mapping: dict[str, str] = {}
    taken: set[str] = set()
    for col in columns:
        canon = _ALIAS_LOOKUP.get(_key(col))
        if canon and canon not in taken:
            mapping[col] = canon
            taken.add(canon)
    return mapping


def read_uploaded(file: IO[bytes] | bytes, filename: str) -> pd.DataFrame:
    """Read a CSV or Excel upload into a raw DataFrame (all columns as text)."""
    data = file if isinstance(file, bytes) else file.read()
    name = filename.lower()
    if name.endswith((".xlsx", ".xlsm", ".xls")):
        return pd.read_excel(io.BytesIO(data), dtype=str, engine="openpyxl")
    for enc in ("utf-8-sig", "cp1256", "latin-1"):
        try:
            return pd.read_csv(io.BytesIO(data), dtype=str, encoding=enc,
                               keep_default_na=False, sep=None, engine="python")
        except UnicodeDecodeError:
            continue
    raise ValueError("Unable to decode the CSV file")


def _clean_str(s: pd.Series) -> pd.Series:
    out = s.astype("object").where(s.notna(), "")
    out = out.map(lambda v: re.sub(r"\s+", " ", str(v)).strip())
    return out.replace({"nan": "", "None": "", "NaN": "", "<NA>": "", "NaT": ""})


def _clean_id(s: pd.Series) -> pd.Series:
    out = _clean_str(s)
    # Excel often turns numeric IDs into floats ("1042.0")
    return out.str.replace(r"^(\d+)\.0$", r"\1", regex=True)


def _map_values(s: pd.Series, mapping: dict[str, str]) -> pd.Series:
    return s.map(lambda v: mapping.get(_key(v), v) if v else "")


def _parse_level(v) -> float:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return np.nan
    m = re.search(r"-?\d+", str(v))
    return float(m.group()) if m else np.nan


def normalize(raw: pd.DataFrame) -> pd.DataFrame:
    """Return a copy of ``raw`` in the canonical schema.

    Adds helper columns:
      * ``node_id``   - unique key used by the hierarchy graph (Employee ID, or
                        ``VAC-<PositionID>`` for vacant positions without one)
      * ``is_vacant`` - Position Status == Vacant
      * ``is_active`` - filled position held by an Active / On Leave employee
      * ``is_duplicate_id`` - second+ occurrence of an Employee ID
      * ``row_number`` - 1-based row number in the source file (for evidence)
    """
    df = raw.copy()
    df = df.rename(columns=map_columns(df.columns))
    df = df.loc[:, ~df.columns.duplicated()]
    for col in CANONICAL_COLUMNS:
        if col not in df.columns:
            df[col] = np.nan
    extra = [c for c in df.columns if c not in CANONICAL_COLUMNS]
    df = df[CANONICAL_COLUMNS + extra].reset_index(drop=True)
    df.insert(0, "row_number", np.arange(1, len(df) + 1))

    for col in STRING_COLUMNS:
        df[col] = _clean_id(df[col]) if col in ("employee_id", "manager_id", "position_id") \
            else _clean_str(df[col])
    df["employment_status"] = _map_values(df["employment_status"], _STATUS_MAP)
    df["position_status"] = _map_values(df["position_status"], _POSITION_MAP)
    df["employment_type"] = _map_values(df["employment_type"], _TYPE_MAP)
    df["work_arrangement"] = _map_values(df["work_arrangement"], _WORK_MAP)

    for col in NUMERIC_COLUMNS:
        if col == "job_level":
            df[col] = df[col].map(_parse_level).astype(float)
        else:
            cleaned = df[col].astype("object").map(
                lambda v: re.sub(r"[,\s]", "", str(v)) if pd.notna(v) else v)
            df[col] = pd.to_numeric(cleaned, errors="coerce")
    for col in DATE_COLUMNS:
        df[col] = pd.to_datetime(df[col], errors="coerce")

    # Position status default: rows without an employee are vacant positions.
    no_status = df["position_status"].eq("")
    df.loc[no_status, "position_status"] = np.where(
        df.loc[no_status, "employee_id"].eq(""), "Vacant", "Filled")
    df["is_vacant"] = df["position_status"].eq("Vacant")
    # Employment status default for filled positions
    df.loc[~df["is_vacant"] & df["employment_status"].eq(""), "employment_status"] = "Active"

    # Node IDs (graph keys)
    node = df["employee_id"].copy()
    vac_no_id = df["is_vacant"] & node.eq("")
    pos = df["position_id"].where(df["position_id"].ne(""), "ROW" + df["row_number"].astype(str))
    node.loc[vac_no_id] = "VAC-" + pos.loc[vac_no_id]
    missing_id = ~df["is_vacant"] & node.eq("")
    node.loc[missing_id] = "NOID-" + df.loc[missing_id, "row_number"].astype(str)
    df.insert(1, "node_id", node)
    df["is_duplicate_id"] = df["node_id"].duplicated(keep="first")
    df["is_active"] = (~df["is_vacant"] & df["employment_status"].isin(["Active", "On Leave"])
                       & ~df["is_duplicate_id"])
    # Years of service: derive from hire date when absent
    if df["years_of_service"].isna().all() and df["hire_date"].notna().any():
        ref = pd.Timestamp.today().normalize()
        df["years_of_service"] = ((ref - df["hire_date"]).dt.days / 365.25).round(1)
    return df
