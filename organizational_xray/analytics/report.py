"""Dataset report - every number is computed from the data (used by the CLI,
the README section and the Import Data page)."""
from __future__ import annotations

import pandas as pd

from analytics.anomalies import detect_findings
from analytics.hierarchy import build_org_model, depth_stats, layer_count
from analytics.span_of_control import span_stats
from data.loader import normalize
from utils.config import Settings


def dataset_facts(df_raw: pd.DataFrame, settings: Settings | None = None) -> dict:
    settings = settings or Settings()
    model = build_org_model(normalize(df_raw))
    d = model.df
    act = d[d["is_active"]]
    findings = detect_findings(model, settings)
    return {
        "records": len(d),
        "active_employees": len(act),
        "terminated_records": int(d["employment_status"].eq("Terminated").sum()),
        "vacant_positions": int(d["is_vacant"].sum()),
        "departments": int(d.loc[d["department"].ne(""), "department"].nunique()),
        "divisions": int(d.loc[d["division"].ne(""), "division"].nunique()),
        "business_units": int(d.loc[d["business_unit"].ne(""), "business_unit"].nunique()),
        "managers": int(act["is_manager"].sum()),
        "layers": layer_count(d),
        "depth": depth_stats(model),
        "span": span_stats(act.loc[act["is_manager"], "direct_reports"]),
        "findings_by_type": findings["type"].value_counts().to_dict(),
        "findings_by_severity": findings["severity"].value_counts().to_dict(),
        "findings_total": len(findings),
        "cycles": model.cycles,
    }


def dataset_report(df_raw: pd.DataFrame, manifest: list[dict] | None = None) -> str:
    f = dataset_facts(df_raw)
    lines = [
        "## Dataset facts (computed)",
        f"- Records: {f['records']:,}",
        f"- Active employees (headcount): {f['active_employees']:,}",
        f"- Vacant positions: {f['vacant_positions']}",
        f"- Terminated records still referenced: {f['terminated_records']}",
        f"- Business units / divisions / departments: {f['business_units']} / {f['divisions']} / {f['departments']}",
        f"- Managers (>= 1 active direct report): {f['managers']}",
        f"- Structural layers: {f['layers']} (depth {f['depth']['min']}–{f['depth']['max']}, "
        f"mean {f['depth']['mean']:.2f}, median {f['depth']['median']:g})",
        f"- Span of control: min {f['span']['min']:g}, P25 {f['span']['p25']:g}, median "
        f"{f['span']['median']:g}, mean {f['span']['mean']:.2f}, P75 {f['span']['p75']:g}, "
        f"max {f['span']['max']:g}",
        f"- Findings (default settings): {f['findings_total']}",
        "",
        "| Finding type | Count |", "|---|---|",
    ]
    lines += [f"| {k} | {v} |" for k, v in sorted(f["findings_by_type"].items())]
    lines += ["", "| Severity | Count |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in f["findings_by_severity"].items()]
    if manifest:
        lines += ["", "## Injected issues (generator manifest)", "",
                  "| Issue | Expected finding | Department | IDs |", "|---|---|---|---|"]
        for m in manifest:
            ids = ", ".join(m["ids"][:4]) + (" …" if len(m["ids"]) > 4 else "")
            lines.append(f"| {m['issue']} | {m['expected_finding']} | {m['department']} | {ids} |")
    return "\n".join(lines)
