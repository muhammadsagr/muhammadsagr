"""Synthetic organisation generator.

The structure is built FIRST (a tree of positions described by department
blueprints), then people are generated with Faker and placed into the
positions. Finally a set of *deliberate* organisational and data-quality issues
is injected, and every injection is recorded in a manifest so the analytics
engine can be verified against it (see ``tests/test_generator.py``).

Run ``python -m data.dummy_generator`` to write the sample dataset and print a
dataset report computed from the data itself.
"""
from __future__ import annotations

import argparse
import itertools
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
from faker import Faker

from utils.config import CANONICAL_COLUMNS

SAMPLE_DIR = Path(__file__).resolve().parent / "sample"


# =========================================================================== blueprints
@dataclass
class Unit:
    """A position template. ``children`` is a list of (count, Unit)."""

    title: str
    level: int
    children: list = field(default_factory=list)
    ics: object = 0  # int | (lo, hi) | [per-instance counts]
    ic_titles: list[str] | None = None


@dataclass
class Dept:
    name: str
    division: str
    business_unit: str
    head: Unit
    ic_titles: list[str]
    vacancy_rate: float
    salary_factor: float
    locations: dict[str, float]
    remote_bias: float = 0.1  # share of Remote among IC work arrangements
    onsite_bias: float = 0.6


def U(title, level, children=(), ics=0, ic_titles=None) -> Unit:
    return Unit(title, level, list(children), ics, ic_titles)


HQ = {"Riyadh": 1.0}
DEPARTMENTS: list[Dept] = [
    # ---------------------------------------------------------------- Human Resources
    Dept("HR Operations", "Human Resources", "Corporate Services",
         U("Director, HR Operations", 2, [(3, U("HR Operations Manager", 4, ics=(15, 18)))]),
         ["HR Officer", "HR Specialist", "HR Analyst", "HR Analyst", "Senior HR Analyst",
          "HR Coordinator"], 0.03, 1.0, {"Riyadh": 0.7, "Jeddah": 0.2, "Dammam": 0.1}),
    # HRIS: deliberately manager-heavy (high management ratio, low spans).
    Dept("HRIS", "Human Resources", "Corporate Services",
         U("Director, HRIS", 2, [(2, U("HRIS Senior Manager", 3,
            [([2, 1], U("HRIS Manager", 4, [(1, U("HRIS Supervisor", 5, ics=[3, 2, 1]))]))]))]),
         ["HRIS Analyst", "HRIS Analyst", "HR Data Analyst", "HRIS Specialist", "Hris Analyst"],
         0.0, 1.1, HQ, remote_bias=0.2, onsite_bias=0.3),
    Dept("Talent Acquisition", "Human Resources", "Corporate Services",
         U("Director, Talent Acquisition", 2, [(2, U("Talent Acquisition Manager", 4, ics=(14, 17)))]),
         ["Recruiter", "Senior Recruiter", "Talent Acquisition Specialist",
          "Talent Acquisition Specialist", "Recruitment Specialist"], 0.08, 0.95,
         {"Riyadh": 0.6, "Jeddah": 0.25, "Dubai": 0.15}),
    Dept("Learning & Development", "Human Resources", "Corporate Services",
         U("Director, Learning & Development", 2, [(2, U("L&D Manager", 4, ics=(8, 10)))]),
         ["Learning & Development Specialist", "Training Specialist", "L&D Specialist",
          "Instructional Designer"], 0.05, 0.95, HQ),
    Dept("Total Rewards", "Human Resources", "Corporate Services",
         U("Head of Total Rewards", 2, ics=2), ["Compensation Analyst", "Benefits Analyst"],
         0.0, 1.05, HQ),
    # ---------------------------------------------------------------- Finance
    Dept("Accounting", "Finance", "Corporate Services",
         U("Director, Accounting", 2, [(2, U("Senior Accounting Manager", 3,
            [(2, U("Accounting Manager", 4, [(3, U("Accounting Supervisor", 5, ics=(5, 8)))]))]))]),
         ["Accountant", "Senior Accountant", "Staff Accountant", "Accounts Payable Accountant",
          "Accounts Receivable Accountant"], 0.04, 1.0, {"Riyadh": 0.85, "Jeddah": 0.15}),
    Dept("Financial Planning", "Finance", "Corporate Services",
         U("Director, Financial Planning", 2, [(2, U("FP&A Manager", 4, ics=(11, 13)))]),
         ["Financial Analyst", "Senior Financial Analyst", "FP&A Analyst"], 0.05, 1.1, HQ),
    Dept("Treasury", "Finance", "Corporate Services",
         U("Treasury Director", 2, ics=1), ["Treasury Analyst"], 0.0, 1.15, HQ),
    Dept("Procurement", "Finance", "Corporate Services",
         U("Director, Procurement", 2, [(3, U("Procurement Manager", 4, ics=[12, 1, 13]))]),
         ["Procurement Specialist", "Buyer", "Senior Buyer", "Category Specialist"], 0.06, 0.95,
         {"Riyadh": 0.6, "Dammam": 0.4}),
    # ---------------------------------------------------------------- Information Technology
    Dept("Infrastructure", "Information Technology", "Technology",
         U("Director, Infrastructure", 2, [(2, U("Senior Infrastructure Manager", 3,
            [(3, U("Infrastructure Manager", 4, ics=(9, 12)))]))]),
         ["Systems Engineer", "Senior Systems Engineer", "Network Engineer", "Cloud Engineer",
          "IT Support Specialist"], 0.07, 1.15, {"Riyadh": 0.8, "Dammam": 0.2},
         remote_bias=0.15, onsite_bias=0.4),
    Dept("Cybersecurity", "Information Technology", "Technology",
         U("Director, Cybersecurity", 2, [(2, U("Senior Security Manager", 3,
            [([2, 1], U("Security Manager", 4, ics=(7, 9)))]))]),
         ["Security Analyst", "Senior Security Analyst", "SOC Analyst", "Security Engineer"],
         0.15, 1.25, HQ, remote_bias=0.1, onsite_bias=0.5),
    Dept("Applications", "Information Technology", "Technology",
         U("Director, Applications", 2, [(3, U("Senior Applications Manager", 3,
            [(3, U("Applications Manager", 4, [(2, U("Team Lead", 5, ics=(5, 8)))]))]))]),
         ["Software Engineer", "Senior Software Engineer", "Software Developer", "QA Engineer",
          "Business Analyst"], 0.06, 1.2, {"Riyadh": 0.7, "Cairo": 0.3},
         remote_bias=0.3, onsite_bias=0.25),
    Dept("Data & Analytics", "Information Technology", "Technology",
         U("Director, Data & Analytics", 2, [(3, U("Analytics Manager", 4, ics=[10, 11, 3]))]),
         ["Data Analyst", "Senior Data Analyst", "BI Analyst", "Data Engineer", "Data Scientist"],
         0.08, 1.2, HQ, remote_bias=0.25, onsite_bias=0.3),
    # ---------------------------------------------------------------- Operations
    # Operations: one deliberately deep branch (VP -> Sr Director -> Director -> ...)
    # next to a flatter plant branch with very wide supervisor spans.
    Dept("Operations", "Operations", "Operations",
         U("VP Operations", 2, [
             (1, U("Senior Director, Field Operations", 2, [
                 (2, U("Director, Regional Operations", 2, [
                     (2, U("Senior Operations Manager", 3, [
                         (3, U("Operations Manager", 4, [
                             (3, U("Operations Supervisor", 5, ics=(8, 11)))]))]))]))])),
             (1, U("Director, Plant Operations", 2, [
                 (3, U("Plant Manager", 4, [
                     (2, U("Shift Supervisor", 5, ics=[14, 11, 20, 12, 22, 10]))]))])),
         ]),
         ["Operations Technician", "Senior Operations Technician", "Machine Operator",
          "Maintenance Technician", "Operations Associate"], 0.02, 0.8,
         {"Dammam": 0.55, "Jubail": 0.45}, remote_bias=0.0, onsite_bias=0.97),
    # Quality: flat - the director manages most ICs directly (high span).
    Dept("Quality", "Operations", "Operations",
         U("Director, Quality", 2, [(1, U("Quality Manager", 4, ics=7))], ics=17),
         ["Quality Inspector", "Quality Engineer", "Quality Analyst", "QA/QC Technician"],
         0.04, 0.9, {"Dammam": 0.6, "Jubail": 0.4}, remote_bias=0.0, onsite_bias=0.9),
    Dept("Supply Chain", "Operations", "Operations",
         U("Director, Supply Chain", 2, [(2, U("Senior Supply Chain Manager", 3,
            [(2, U("Supply Chain Manager", 4, [(3, U("Warehouse Supervisor", 5,
                                                   ics=[9, 11, 20, 10, 12, 8, 15, 10, 11, 9, 12, 10]))]))]))]),
         ["Warehouse Associate", "Logistics Coordinator", "Inventory Specialist",
          "Forklift Operator", "Supply Chain Analyst"], 0.03, 0.8,
         {"Dammam": 0.5, "Jeddah": 0.3, "Riyadh": 0.2}, remote_bias=0.0, onsite_bias=0.9),
    Dept("Customer Operations", "Operations", "Operations",
         U("Director, Customer Operations", 2, [(3, U("Customer Operations Manager", 4,
            [(3, U("Customer Service Supervisor", 5, ics=[12, 10, 34, 11, 9, 13, 12, 11, 10]))]))]),
         ["Customer Service Agent", "Senior Customer Service Agent",
          "Customer Support Specialist", "Call Center Agent"], 0.05, 0.7,
         {"Riyadh": 0.5, "Cairo": 0.5}, remote_bias=0.15, onsite_bias=0.6),
    # ---------------------------------------------------------------- Commercial
    Dept("Sales", "Commercial", "Commercial",
         U("Director, Sales", 2, [(3, U("Regional Sales Director", 3,
            [(3, U("Sales Manager", 4, ics=(8, 11)))]))]),
         ["Sales Representative", "Senior Sales Representative", "Account Executive",
          "Key Account Manager", "Sales Executive"], 0.05, 1.0,
         {"Riyadh": 0.4, "Jeddah": 0.35, "Dubai": 0.25}, remote_bias=0.05, onsite_bias=0.5),
    Dept("Marketing", "Commercial", "Commercial",
         U("Director, Marketing", 2, [(3, U("Marketing Manager", 4, ics=(9, 11)))]),
         ["Marketing Specialist", "Digital Marketing Specialist", "Content Specialist",
          "Marketing Analyst", "Brand Specialist"], 0.06, 1.0, {"Riyadh": 0.7, "Dubai": 0.3},
         remote_bias=0.2, onsite_bias=0.3),
    Dept("Business Development", "Commercial", "Commercial",
         U("Director, Business Development", 2, ics=11),
         ["Business Development Executive", "Partnership Specialist",
          "Business Development Analyst"], 0.0, 1.1, {"Riyadh": 0.6, "Dubai": 0.4}),
    # ---------------------------------------------------------------- Governance (CEO direct)
    Dept("Internal Audit", "Governance", "Corporate Services",
         U("Head of Internal Audit", 2, ics=2), ["Internal Auditor"], 0.0, 1.1, HQ),
    Dept("Strategy Office", "Governance", "Corporate Services",
         U("Strategy Director", 2), [], 0.0, 1.2, HQ),
]

C_SUITE = {
    "Human Resources": "Chief Human Resources Officer",
    "Finance": "Chief Financial Officer",
    "Information Technology": "Chief Information Officer",
    "Operations": "Chief Operating Officer",
    "Commercial": "Chief Commercial Officer",
}
EXEC_DEPT = ("Executive Office", "Executive Office", "Corporate Services")
ESG_DEPT = ("ESG & Sustainability", "Governance", "Corporate Services")

BASE_SALARY = {0: 1_800_000, 1: 950_000, 2: 480_000, 3: 330_000, 4: 245_000, 5: 170_000, 6: 110_000}
GRADE_RANGE = {0: (20, 20), 1: (18, 19), 2: (16, 17), 3: (14, 15), 4: (12, 13), 5: (10, 11), 6: (5, 9)}
AGE_BY_LEVEL = {0: 56, 1: 51, 2: 46, 3: 42, 4: 39, 5: 36, 6: 31}


# =========================================================================== builder
class _Builder:
    def __init__(self, seed: int, as_of: date, scale: float, locale: str):
        self.rng = np.random.default_rng(seed)
        self.fake = Faker(locale)
        self.fake.seed_instance(seed)
        self.as_of = as_of
        self.scale = scale
        self.rows: list[dict] = []
        self._pos_seq = itertools.count(10001)
        self._instance_counter: dict[tuple, int] = {}

    # ---------------------------------------------------------------- helpers
    def _count(self, spec, key: tuple | None = None, scale: float = 1.0) -> int:
        if isinstance(spec, list):
            i = self._instance_counter.get(key, 0)
            self._instance_counter[key] = i + 1
            n = spec[i % len(spec)]
        elif isinstance(spec, tuple):
            n = int(self.rng.integers(spec[0], spec[1] + 1))
        else:
            n = int(spec)
        return max(0, int(round(n * scale))) if n else 0

    def _person(self, level: int) -> dict:
        gender = "Male" if self.rng.random() < 0.64 else "Female"
        first = self.fake.first_name_male() if gender == "Male" else self.fake.first_name_female()
        age = int(np.clip(self.rng.normal(AGE_BY_LEVEL[level], 5.5), 21, 64))
        max_yos = max(0, min(age - 21, 28))
        yos = float(np.clip(self.rng.gamma(2.2, 2.6 + (6 - level) * 0.9), 0.1, max_yos or 0.1))
        hire = self.as_of - timedelta(days=int(yos * 365.25))
        return {
            "employee_name": f"{first} {self.fake.last_name()}",
            "gender": gender,
            "age": age,
            "hire_date": pd.Timestamp(hire),
            "years_of_service": round(yos, 1),
        }

    def _add(self, *, title, level, dept_name, division, bu, manager_id, location,
             salary_factor=1.0, vacant=False, work=None, emp_type=None) -> dict:
        pos_id = f"P{next(self._pos_seq)}"
        row = {c: None for c in CANONICAL_COLUMNS}
        row.update(job_title=title, job_level=level, department=dept_name, division=division,
                   business_unit=bu, manager_id=manager_id, location=location, position_id=pos_id)
        lo, hi = GRADE_RANGE[level]
        grade = int(self.rng.integers(lo, hi + 1))
        if level == 6 and title.lower().startswith("senior"):
            grade = min(hi + 1, grade + 1)
        row["grade"] = f"G{grade}"
        if vacant:
            row.update(position_status="Vacant", employee_id="", employee_name="",
                       employment_status="", employment_type="", work_arrangement="")
        else:
            row.update(self._person(level))
            row["position_status"] = "Filled"
            row["employment_status"] = "On Leave" if self.rng.random() < 0.035 else "Active"
            row["employment_type"] = emp_type or (
                self.rng.choice(["Full-Time", "Contractor", "Part-Time"], p=[0.86, 0.10, 0.04])
                if level == 6 else "Full-Time")
            row["work_arrangement"] = work or "On-site"
            sal = (BASE_SALARY[level] * salary_factor * self.rng.lognormal(0, 0.10)
                   * (1 + 0.012 * row["years_of_service"]))
            if level == 6 and title.lower().startswith("senior"):
                sal *= 1.2
            row["salary"] = float(round(sal, -2))
            row["performance_rating"] = int(self.rng.choice([1, 2, 3, 4, 5],
                                                             p=[0.04, 0.14, 0.50, 0.24, 0.08]))
        self.rows.append(row)
        return row

    def _loc(self, dept: Dept, parent_loc: str | None) -> str:
        if parent_loc and self.rng.random() < 0.8 and parent_loc in dept.locations:
            return parent_loc
        names = list(dept.locations)
        p = np.array(list(dept.locations.values()), dtype=float)
        return str(self.rng.choice(names, p=p / p.sum()))

    def _work(self, dept: Dept, level: int) -> str:
        if level <= 3:
            return "On-site" if self.rng.random() < 0.7 else "Hybrid"
        r = self.rng.random()
        if r < dept.remote_bias:
            return "Remote"
        return "On-site" if r < dept.remote_bias + dept.onsite_bias else "Hybrid"

    def _node_id(self, row: dict) -> str:
        return row["employee_id"] or f"VAC-{row['position_id']}"

    # ---------------------------------------------------------------- recursion
    def _build_unit(self, unit: Unit, dept: Dept, manager_id: str, parent_loc: str | None,
                    is_head: bool) -> None:
        loc = self._loc(dept, parent_loc)
        row = self._add(title=unit.title, level=unit.level, dept_name=dept.name,
                        division=dept.division, bu=dept.business_unit, manager_id=manager_id,
                        location=loc, salary_factor=dept.salary_factor,
                        work=self._work(dept, unit.level))
        row["employee_id"] = self._next_emp_id()
        my_id = row["employee_id"]
        child_scale = self.scale if is_head else 1.0
        for count_spec, child in unit.children:
            n = self._count(count_spec, ("c", id(count_spec)), child_scale)
            for _ in range(n):
                self._build_unit(child, dept, my_id, loc, False)
        # individual contributors
        ic_scale = self.scale if (is_head and not unit.children) else 1.0
        n_ic = self._count(unit.ics, ("i", id(unit)), ic_scale)
        titles = unit.ic_titles or dept.ic_titles
        for _ in range(n_ic):
            vacant = self.rng.random() < dept.vacancy_rate
            ic = self._add(title=str(self.rng.choice(titles)), level=6, dept_name=dept.name,
                           division=dept.division, bu=dept.business_unit, manager_id=my_id,
                           location=self._loc(dept, loc), salary_factor=dept.salary_factor,
                           vacant=vacant, work=self._work(dept, 6))
            if not vacant:
                ic["employee_id"] = self._next_emp_id()

    def _next_emp_id(self) -> str:
        return self._emp_ids.pop()

    # ---------------------------------------------------------------- top level
    def build(self) -> pd.DataFrame:
        # Pre-shuffle a pool of employee IDs so IDs do not reveal the structure.
        pool = np.arange(10001, 10001 + int(3000 * max(self.scale, 1.0)) + 2000)
        self.rng.shuffle(pool)
        self._emp_ids = [f"E{n}" for n in pool]

        ex_name, ex_div, ex_bu = EXEC_DEPT
        ceo = self._add(title="Chief Executive Officer", level=0, dept_name=ex_name,
                        division=ex_div, bu=ex_bu, manager_id="", location="Riyadh",
                        work="On-site", emp_type="Full-Time")
        ceo["employee_id"] = self._next_emp_id()
        ceo_id = ceo["employee_id"]
        for _ in range(2):
            ea = self._add(title="Executive Assistant", level=6, dept_name=ex_name,
                           division=ex_div, bu=ex_bu, manager_id=ceo_id, location="Riyadh",
                           work="On-site", emp_type="Full-Time")
            ea["employee_id"] = self._next_emp_id()

        for division, title in C_SUITE.items():
            cx = self._add(title=title, level=1, dept_name=ex_name, division=ex_div, bu=ex_bu,
                           manager_id=ceo_id, location="Riyadh", work="On-site",
                           emp_type="Full-Time")
            cx["employee_id"] = self._next_emp_id()
            ea = self._add(title="Executive Assistant", level=6, dept_name=ex_name,
                           division=ex_div, bu=ex_bu, manager_id=cx["employee_id"],
                           location="Riyadh", work="On-site", emp_type="Full-Time")
            ea["employee_id"] = self._next_emp_id()
            for dept in (d for d in DEPARTMENTS if d.division == division):
                self._build_unit(dept.head, dept, cx["employee_id"], "Riyadh", True)

        for dept in (d for d in DEPARTMENTS if d.division == "Governance"):
            self._build_unit(dept.head, dept, ceo_id, "Riyadh", True)

        # ESG & Sustainability: an "empty" department - only vacant positions.
        esg_name, esg_div, esg_bu = ESG_DEPT
        head = self._add(title="Head of ESG & Sustainability", level=2, dept_name=esg_name,
                         division=esg_div, bu=esg_bu, manager_id=ceo_id, location="Riyadh",
                         vacant=True)
        self._add(title="ESG Analyst", level=6, dept_name=esg_name, division=esg_div,
                  bu=esg_bu, manager_id=self._node_id(head), location="Riyadh", vacant=True)

        df = pd.DataFrame(self.rows, columns=CANONICAL_COLUMNS)
        return df


# =========================================================================== injections
def _set_manager(df: pd.DataFrame, idx, manager_id: str, name_lookup: dict) -> None:
    df.loc[idx, "manager_id"] = manager_id
    df.loc[idx, "manager_name"] = name_lookup.get(manager_id, "")


def _inject_issues(df: pd.DataFrame, rng: np.random.Generator, fake: Faker) -> list[dict]:
    """Inject deliberate anomalies. Returns the manifest of what was injected."""
    manifest: list[dict] = []
    names = dict(zip(df["employee_id"], df["employee_name"]))
    used: set = set()

    def pick_ics(dept: str, n: int, exclude_mgrs: set | None = None) -> list:
        filled = df["position_status"].eq("Filled")
        cand = df.index[filled & df["department"].eq(dept) & df["job_level"].eq(6)
                        & ~df.index.isin(list(used))
                        & ~df["employee_id"].isin(set(df["manager_id"]))]
        if exclude_mgrs:
            cand = cand[~df.loc[cand, "manager_id"].isin(exclude_mgrs)]
        chosen = list(rng.choice(cand, size=n, replace=False))
        used.update(chosen)
        return chosen

    # 1. Orphans: no Manager ID -------------------------------------------------------
    for dept in ["Sales", "Infrastructure", "Supply Chain"]:
        (i,) = pick_ics(dept, 1)
        df.loc[i, ["manager_id", "manager_name"]] = ["", ""]
        manifest.append({"issue": "Missing Manager ID", "expected_finding": "ORPHAN_EMPLOYEE",
                         "ids": [df.at[i, "employee_id"]], "department": dept})

    # 2. Manager ID that does not exist ----------------------------------------------
    for k, dept in enumerate(["Talent Acquisition", "Applications", "Customer Operations"]):
        (i,) = pick_ics(dept, 1)
        ghost = f"E{90001 + k}"
        df.loc[i, ["manager_id", "manager_name"]] = [ghost, fake.name()]
        manifest.append({"issue": "Manager ID not found", "expected_finding": "INVALID_MANAGER",
                         "ids": [df.at[i, "employee_id"]], "department": dept,
                         "detail": ghost})

    # 3. Managers who are terminated but still have reports ---------------------------
    for dept, title in [("Customer Operations", "Customer Service Supervisor"),
                        ("Marketing", "Marketing Manager")]:
        cand = df.index[df["department"].eq(dept) & df["job_title"].eq(title)]
        # choose a supervisor with a normal team (keep the 34-span one intact)
        sizes = df["manager_id"].value_counts()
        cand = [c for c in cand if 3 <= sizes.get(df.at[c, "employee_id"], 0) <= 13]
        i = cand[0]
        df.loc[i, "employment_status"] = "Terminated"  # position left as "Filled" (stale)
        reports = df.index[df["manager_id"].eq(df.at[i, "employee_id"])
                           & df["position_status"].eq("Filled")].tolist()
        used.update(reports)
        manifest.append({"issue": "Reports point to a terminated manager",
                         "expected_finding": "TERMINATED_MANAGER",
                         "ids": df.loc[reports, "employee_id"].tolist(), "department": dept,
                         "detail": df.at[i, "employee_id"]})

    # 4. Circular reporting A -> B -> C -> A and a self-reporting record ---------------
    a, b, c = pick_ics("Marketing", 3)
    ida, idb, idc = (df.at[x, "employee_id"] for x in (a, b, c))
    _set_manager(df, a, idb, names)
    _set_manager(df, b, idc, names)
    _set_manager(df, c, ida, names)
    manifest.append({"issue": "Circular reporting (3-cycle)",
                     "expected_finding": "CIRCULAR_REPORTING", "ids": [ida, idb, idc],
                     "department": "Marketing"})
    (s,) = pick_ics("Data & Analytics", 1)
    _set_manager(df, s, df.at[s, "employee_id"], names)
    manifest.append({"issue": "Self-reporting (1-cycle)", "expected_finding": "CIRCULAR_REPORTING",
                     "ids": [df.at[s, "employee_id"]], "department": "Data & Analytics"})

    # 5. Duplicate Position IDs -------------------------------------------------------
    for dept in ["Accounting", "Sales"]:
        x, y = pick_ics(dept, 2)
        df.loc[y, "position_id"] = df.at[x, "position_id"]
        manifest.append({"issue": "Duplicate Position ID", "expected_finding": "DUPLICATE_POSITION",
                         "ids": [df.at[x, "employee_id"], df.at[y, "employee_id"]],
                         "department": dept, "detail": df.at[x, "position_id"]})

    # 6. A team lead whose whole team is vacant (manager-level, zero active reports) --
    tls = df.index[df["job_title"].eq("Team Lead")]
    tl = tls[0]
    team = df.index[df["manager_id"].eq(df.at[tl, "employee_id"])]
    df.loc[team, ["position_status", "employee_id", "employee_name", "employment_status",
                  "employment_type", "work_arrangement"]] = ["Vacant", "", "", "", "", ""]
    df.loc[team, ["salary", "age", "performance_rating", "years_of_service"]] = np.nan
    df.loc[team, "hire_date"] = pd.NaT
    manifest.append({"issue": "Manager-level position with no active reports (team vacant)",
                     "expected_finding": "VACANT_POSITION", "ids": [df.at[tl, "employee_id"]],
                     "department": "Applications", "detail": f"{len(team)} vacant positions"})

    # 7. Data-quality defects ---------------------------------------------------------
    (i,) = pick_ics("HR Operations", 1)
    df.loc[i, "job_title"] = "hr analyst"  # case variant of an existing title
    manifest.append({"issue": "Job title case variant ('hr analyst')",
                     "expected_finding": "DUPLICATE_POSITION", "ids": [df.at[i, "employee_id"]],
                     "department": "HR Operations"})
    for dept in ["Procurement", "Quality"]:
        (i,) = pick_ics(dept, 1)
        df.loc[i, "job_title"] = ""
        manifest.append({"issue": "Missing job title", "expected_finding": "DATA_QUALITY",
                         "ids": [df.at[i, "employee_id"]], "department": dept})
    for dept in ["Supply Chain", "Customer Operations", "Sales"]:
        (i,) = pick_ics(dept, 1)
        df.loc[i, "salary"] = np.nan
        manifest.append({"issue": "Missing salary", "expected_finding": "DATA_QUALITY",
                         "ids": [df.at[i, "employee_id"]], "department": dept})
    (i,) = pick_ics("Operations", 1)
    df.loc[i, "salary"] = 0.0
    manifest.append({"issue": "Salary = 0", "expected_finding": "DATA_QUALITY",
                     "ids": [df.at[i, "employee_id"]], "department": "Operations"})
    (i,) = pick_ics("Applications", 1)
    df.loc[i, "department"] = ""
    manifest.append({"issue": "Missing department", "expected_finding": "DATA_QUALITY",
                     "ids": [df.at[i, "employee_id"]], "department": "Applications"})

    # 8. Duplicate employee ID (a second record re-using an existing ID) --------------
    (i,) = pick_ics("Accounting", 1)
    dup = df.loc[[i]].copy()
    dup["employee_name"] = fake.name()
    dup["position_id"] = "P99001"
    df_dup_idx = len(df)
    df.loc[df_dup_idx] = dup.iloc[0].values
    manifest.append({"issue": "Duplicate Employee ID", "expected_finding": "DATA_QUALITY",
                     "ids": [df.at[i, "employee_id"]], "department": "Accounting"})
    return manifest


# =========================================================================== public API
def generate_org(n_employees: int = 1500, seed: int = 42, as_of: date | None = None,
                 locale: str = "en_US", inject_issues: bool = True
                 ) -> tuple[pd.DataFrame, list[dict]]:
    """Build a synthetic organisation of roughly ``n_employees`` active employees.

    Returns ``(dataframe, manifest)`` - the manifest lists every injected issue.
    """
    as_of = as_of or date.today()
    base = 1500
    scale = max(0.3, n_employees / base)
    builder = _Builder(seed, as_of, scale, locale)
    df = builder.build()
    manifest = _inject_issues(df, builder.rng, builder.fake) if inject_issues else []
    # Manager Name is looked up from the (possibly stale) manager record.
    names = dict(zip(df["employee_id"], df["employee_name"]))
    keep = df["manager_name"].notna() & df["manager_name"].ne("")
    df.loc[~keep, "manager_name"] = df.loc[~keep, "manager_id"].map(names).fillna("")
    vac_names = {f"VAC-{p}": "(Vacant)" for p in df.loc[df["position_status"].eq("Vacant"),
                                                         "position_id"]}
    df.loc[df["manager_id"].isin(vac_names), "manager_name"] = "(Vacant)"
    df = df.reset_index(drop=True)
    df["job_level"] = df["job_level"].astype("Int64")
    for col in ("age", "performance_rating"):
        df[col] = pd.to_numeric(df[col]).astype("Int64")
    df["years_of_service"] = pd.to_numeric(df["years_of_service"])
    df["salary"] = pd.to_numeric(df["salary"])
    return df, manifest


def save_sample(df: pd.DataFrame, out_dir: Path = SAMPLE_DIR) -> dict[str, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / "org_dummy_data.csv"
    xlsx_path = out_dir / "org_dummy_data.xlsx"
    df.to_csv(csv_path, index=False, encoding="utf-8-sig")
    df.to_excel(xlsx_path, index=False, engine="openpyxl")
    return {"csv": csv_path, "xlsx": xlsx_path}


def _main() -> None:
    parser = argparse.ArgumentParser(description="Generate the Organizational X-Ray dataset")
    parser.add_argument("--employees", type=int, default=1500)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--no-save", action="store_true")
    args = parser.parse_args()
    df, manifest = generate_org(args.employees, args.seed)
    if not args.no_save:
        paths = save_sample(df)
        print("Saved:", ", ".join(str(p) for p in paths.values()))
    from analytics.report import dataset_report

    print(dataset_report(df, manifest))


if __name__ == "__main__":
    _main()
