import sys
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from analytics.hierarchy import build_org_model  # noqa: E402
from data.dummy_generator import generate_org  # noqa: E402
from data.loader import normalize  # noqa: E402


def make_raw(rows):
    """rows: (id, manager, title, level, department[, status[, position_status[, position_id]]])"""
    out = []
    for i, r in enumerate(rows):
        r = list(r) + [None] * (8 - len(r))
        emp, mgr, title, level, dept, status, pstat, pid = r
        out.append({
            "EmployeeID": emp, "EmployeeName": f"Name {emp}" if emp else "", "ManagerID": mgr,
            "JobTitle": title, "JobLevel": level, "Department": dept, "Division": "Div",
            "BusinessUnit": "BU", "Salary": 100000 - 1000 * level, "EmploymentStatus": status or "Active",
            "PositionID": pid or f"P{i + 1:04d}", "PositionStatus": pstat or "Filled",
        })
    return pd.DataFrame(out)


def make_model(rows):
    return build_org_model(normalize(make_raw(rows)))


# A small, valid organisation:
#   C (CEO) -> A (dir, Sales) -> M1 (mgr) -> e1..e5
#                             -> M2 (mgr) -> e6
#           -> B (dir, Ops)   -> e7, e8
SMALL = [
    ("C", "", "Chief Executive Officer", 0, "Exec"),
    ("A", "C", "Sales Director", 2, "Sales"),
    ("B", "C", "Ops Director", 2, "Ops"),
    ("M1", "A", "Sales Manager", 4, "Sales"),
    ("M2", "A", "Sales Manager", 4, "Sales"),
    ("e1", "M1", "Sales Rep", 6, "Sales"),
    ("e2", "M1", "Sales Rep", 6, "Sales"),
    ("e3", "M1", "Sales Rep", 6, "Sales"),
    ("e4", "M1", "Sales Rep", 6, "Sales"),
    ("e5", "M1", "Sales Rep", 6, "Sales"),
    ("e6", "M2", "Sales Rep", 6, "Sales"),
    ("e7", "B", "Operator", 6, "Ops"),
    ("e8", "B", "Operator", 6, "Ops"),
]


@pytest.fixture
def small_rows():
    return list(SMALL)


@pytest.fixture(scope="session")
def dummy():
    df, manifest = generate_org(1500, 42, as_of=date(2026, 1, 1))
    return df, manifest


@pytest.fixture(scope="session")
def dummy_model(dummy):
    return build_org_model(normalize(dummy[0]))
