"""OrgXRayEngine - a single, UI-independent facade over the analytics layer.

This is the integration point for a future AI assistant: the assistant should
*call these tools* (see ``TOOL_SPECS`` / ``call_tool``) and narrate their
results, never compute numbers itself. Every tool returns plain JSON-friendly
data that is traceable to records in the dataset.
"""
from __future__ import annotations

import json
from functools import cached_property

import numpy as np
import pandas as pd

from analytics.anomalies import detect_findings, explain_finding
from analytics.data_quality import run_checks
from analytics.departments import job_title_analysis, layer_metrics, unit_metrics
from analytics.hierarchy import OrgModel, build_org_model, depth_stats, longest_chains
from analytics.simulations import apply_scenario, compare, org_summary
from analytics.span_of_control import manager_table, span_stats
from data.loader import normalize
from utils.config import Settings


def _records(df: pd.DataFrame, limit: int | None = 50) -> list[dict]:
    d = df.head(limit) if limit else df
    return json.loads(d.to_json(orient="records", date_format="iso", default_handler=str))


class OrgXRayEngine:
    def __init__(self, data: pd.DataFrame, settings: Settings | None = None,
                 normalized: bool = False, model: OrgModel | None = None):
        self.df = data if normalized else normalize(data)
        self.settings = settings or Settings()
        self._model = model

    # ------------------------------------------------------------------ core objects
    @property
    def model(self) -> OrgModel:
        if self._model is None:
            self._model = build_org_model(self.df)
        return self._model

    @cached_property
    def findings(self) -> pd.DataFrame:
        return detect_findings(self.model, self.settings)

    # ------------------------------------------------------------------ tools
    def summary(self) -> dict:
        s = org_summary(self.model, self.settings)
        s["Findings"] = len(self.findings)
        return {k: (None if isinstance(v, float) and np.isnan(v) else v) for k, v in s.items()}

    def departments_by(self, metric: str = "management_ratio", top: int = 10,
                       ascending: bool = False) -> list[dict]:
        u = unit_metrics(self.model.df, "department", self.settings)
        if metric not in u.columns:
            raise ValueError(f"Unknown metric '{metric}'. Options: {list(u.columns)}")
        return _records(u.sort_values(metric, ascending=ascending), top)

    def managers_by_span(self, min_reports: int | None = None, max_reports: int | None = None,
                         department: str | None = None) -> list[dict]:
        m = manager_table(self.model.df, self.settings)
        if min_reports is not None:
            m = m[m["direct_reports"] >= min_reports]
        if max_reports is not None:
            m = m[m["direct_reports"] <= max_reports]
        if department:
            m = m[m["department"].eq(department)]
        return _records(m, None)

    def span_statistics(self) -> dict:
        return span_stats(self.model.df.loc[self.model.df["is_manager"], "direct_reports"])

    def depth_statistics(self) -> dict:
        return depth_stats(self.model)

    def layers(self, basis: str = "job_level") -> list[dict]:
        return _records(layer_metrics(self.model.df, basis), None)

    def longest_reporting_chains(self, top: int = 10) -> list[dict]:
        return _records(longest_chains(self.model, top), None)

    def list_findings(self, finding_type: str | None = None, severity: str | None = None,
                      department: str | None = None, limit: int = 50) -> list[dict]:
        f = self.findings
        if finding_type:
            f = f[f["type"].eq(finding_type)]
        if severity:
            f = f[f["severity"].eq(severity)]
        if department:
            f = f[f["department"].eq(department)]
        return _records(f.drop(columns=["related_ids"]), limit)

    def explain(self, finding_id: str) -> dict:
        e = explain_finding(self.findings, finding_id, self.model)
        recs = e.pop("records")
        e["records"] = _records(recs[["node_id", "employee_name", "job_title", "department",
                                      "manager_id", "direct_reports", "depth",
                                      "reporting_status"]], 30)
        return e

    def explain_department(self, department: str) -> dict:
        u = unit_metrics(self.model.df, "department", self.settings)
        row = u[u["department"].eq(department)]
        if row.empty:
            raise ValueError(f"Department '{department}' not found")
        f = self.findings
        return {"metrics": _records(row)[0],
                "findings": _records(f[f["department"].eq(department)]
                                     .drop(columns=["related_ids"]), None),
                "thresholds": self.settings.as_dict()}

    def employee(self, employee_id: str) -> dict:
        r = self.model.node(employee_id)
        if r is None:
            raise ValueError(f"Employee '{employee_id}' not found")
        return {"record": _records(r.to_frame().T)[0],
                "chain_up": self.model.chain_up(employee_id),
                "direct_reports": self.model.direct_report_ids(employee_id),
                "total_reports": int(r["total_reports"])}

    def simulate(self, actions: list[dict]) -> dict:
        res = apply_scenario(self.df, actions, self.model)
        cmp = compare(self.model, res.model, self.settings)
        return {"log": res.log, "narrative": cmp["narrative"],
                "summary": _records(cmp["summary"][["Metric", "Before (fmt)", "After (fmt)"]], None),
                "department_changes": _records(cmp["department_changes"], 50),
                "span_changes": _records(cmp["span_changes"], 50)}

    def data_quality(self) -> list[dict]:
        return _records(run_checks(self.model).drop(columns=["failing_rows"]), None)

    def job_titles(self) -> dict:
        jt = job_title_analysis(self.model.df, self.settings)
        return {"variants": _records(jt["variants"], None), "similar": _records(jt["similar"], None)}


# ============================================================================ tool registry
TOOL_SPECS: list[dict] = [
    {"name": "summary", "description": "Organisation-level KPIs (headcount, managers, layers, spans, vacancies, findings).",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "departments_by", "description": "Departments ranked by a metric, e.g. management_ratio, headcount, avg_span, layers, vacancy_rate.",
     "parameters": {"type": "object", "properties": {
         "metric": {"type": "string"}, "top": {"type": "integer"}, "ascending": {"type": "boolean"}}}},
    {"name": "managers_by_span", "description": "Managers filtered by number of direct reports.",
     "parameters": {"type": "object", "properties": {
         "min_reports": {"type": "integer"}, "max_reports": {"type": "integer"},
         "department": {"type": "string"}}}},
    {"name": "span_statistics", "description": "Min/max/mean/median/P25/P75 span of control.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "depth_statistics", "description": "Min/max/mean/median organisational depth.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "layers", "description": "Per-layer metrics; basis = job_level or depth.",
     "parameters": {"type": "object", "properties": {"basis": {"type": "string", "enum": ["job_level", "depth"]}}}},
    {"name": "longest_reporting_chains", "description": "The deepest reporting chains with full path.",
     "parameters": {"type": "object", "properties": {"top": {"type": "integer"}}}},
    {"name": "list_findings", "description": "X-Ray findings filtered by type / severity / department.",
     "parameters": {"type": "object", "properties": {
         "finding_type": {"type": "string"}, "severity": {"type": "string"},
         "department": {"type": "string"}, "limit": {"type": "integer"}}}},
    {"name": "explain", "description": "Rule, evidence, thresholds and source records behind a finding.",
     "parameters": {"type": "object", "properties": {"finding_id": {"type": "string"}}, "required": ["finding_id"]}},
    {"name": "explain_department", "description": "Metrics and findings of one department (e.g. why it is a Deep Hierarchy).",
     "parameters": {"type": "object", "properties": {"department": {"type": "string"}}, "required": ["department"]}},
    {"name": "employee", "description": "Profile, reporting chain and reports of an employee.",
     "parameters": {"type": "object", "properties": {"employee_id": {"type": "string"}}, "required": ["employee_id"]}},
    {"name": "simulate", "description": "Run a What-If scenario (list of actions) and return before/after.",
     "parameters": {"type": "object", "properties": {"actions": {"type": "array", "items": {"type": "object"}}},
                    "required": ["actions"]}},
    {"name": "data_quality", "description": "Data quality checks with scores.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "job_titles", "description": "Duplicate and similar job titles.",
     "parameters": {"type": "object", "properties": {}}},
]


def call_tool(engine: OrgXRayEngine, name: str, arguments: dict | None = None):
    """Dispatch a tool call (as an LLM would issue it) to the engine."""
    allowed = {t["name"] for t in TOOL_SPECS}
    if name not in allowed:
        raise ValueError(f"Unknown tool '{name}'")
    return getattr(engine, name)(**(arguments or {}))
