"""What-If Simulator.

A *scenario* is a list of JSON-serialisable actions applied, in order, to a
COPY of the normalised dataset. The source data is never modified. After the
scenario is applied the whole analytics pipeline is re-run and compared with
the baseline, so every "after" number comes from the same engine as "before".

Supported actions::

    {"type": "merge_departments", "departments": ["HRIS", "HR Operations"],
     "new_name": "HR Operations & HRIS", "consolidate_heads": true, "primary_head": null}
    {"type": "remove_layer", "job_level": 5, "department": "HRIS"}   # department optional
    {"type": "move_employee", "employee_id": "E101", "new_manager_id": "E204",
     "move_department": true}
    {"type": "remove_manager", "manager_id": "E101",
     "reassign_to": "manager_of_removed" | "department_head" | "<employee id>"}
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from analytics.departments import unit_metrics
from analytics.hierarchy import OrgModel, build_org_model, department_heads, layer_count
from utils.config import INVALID_REPORTING_STATUSES, Settings
from utils.helpers import safe_div


class SimulationError(ValueError):
    """Raised when an action cannot be applied (the message is user-facing)."""


@dataclass
class ScenarioResult:
    df: pd.DataFrame
    model: OrgModel
    log: list[str] = field(default_factory=list)


# ============================================================================ helpers
def _row_ix(df: pd.DataFrame, node_id: str) -> int:
    ix = df.index[df["node_id"].eq(node_id) & ~df["is_duplicate_id"]]
    if len(ix) == 0:
        raise SimulationError(f"الرقم {node_id} غير موجود في البيانات.")
    return ix[0]


def _set_manager(df: pd.DataFrame, rows, new_manager: str) -> None:
    name = df.loc[df["node_id"].eq(new_manager), "employee_name"]
    df.loc[rows, "manager_id"] = new_manager
    df.loc[rows, "manager_name"] = name.iloc[0] if len(name) else ""


def _children_rows(df: pd.DataFrame, node_id: str) -> pd.Index:
    """All records (active or vacant) whose manager is ``node_id``."""
    return df.index[df["manager_id"].eq(node_id) & df["node_id"].ne(node_id)
                    & (df["is_active"] | df["is_vacant"])]


# ============================================================================ actions
def merge_departments(df: pd.DataFrame, model: OrgModel, departments: list[str], new_name: str,
                      consolidate_heads: bool = False, primary_head: str | None = None
                      ) -> tuple[pd.DataFrame, list[str]]:
    departments = [d for d in departments if d]
    if len(departments) < 2:
        raise SimulationError("اختر إدارتين على الأقل للدمج.")
    missing = [d for d in departments if d not in set(df["department"])]
    if missing:
        raise SimulationError(f"إدارات غير موجودة: {', '.join(missing)}")
    new_name = (new_name or " & ".join(departments)).strip()
    df = df.copy()
    log = []
    heads = department_heads(model)
    primary_dept = departments[0]
    mask = df["department"].isin(departments)
    div = df.loc[df["department"].eq(primary_dept), "division"].mode()
    bu = df.loc[df["department"].eq(primary_dept), "business_unit"].mode()
    df.loc[mask, "department"] = new_name
    if len(div):
        df.loc[mask, "division"] = div.iloc[0]
    if len(bu):
        df.loc[mask, "business_unit"] = bu.iloc[0]
    log.append(f"دمج {' + '.join(departments)} → {new_name} ({int(mask.sum())} سجل).")

    if consolidate_heads:
        primary = primary_head or heads.get(primary_dept)
        if primary is None:
            raise SimulationError("تعذر تحديد رئيس الإدارة الأساسية.")
        for d in departments:
            h = heads.get(d)
            if h is None or h == primary:
                continue
            rows = _children_rows(df, h)
            _set_manager(df, rows, primary)
            df = df.drop(index=_row_ix(df, h))
            log.append(f"توحيد القيادة: {len(rows)} سجل كان يتبع {h} أصبح يتبع {primary}، "
                       f"وتم حذف وظيفة رئيس الإدارة {h}.")
    return df, log


def remove_layer(df: pd.DataFrame, model: OrgModel, job_level: int,
                 department: str | None = None) -> tuple[pd.DataFrame, list[str]]:
    """Remove every *manager* at ``job_level`` (optionally within one department).

    Their reports move up to the nearest remaining manager in their chain.
    """
    m = model.df
    target_mask = m["is_manager"] & m["job_level"].eq(job_level) & m["node_id"].ne(model.ceo_id)
    if department:
        target_mask &= m["department"].eq(department)
    targets = set(m.loc[target_mask, "node_id"])
    if not targets:
        raise SimulationError("لا يوجد مديرون في الطبقة/الإدارة المحددة.")
    df = df.copy()
    moved = 0
    new_parent = {}
    for t in targets:
        chain = model.chain_up(t)[1:]
        parent = next((c for c in chain if c not in targets), None)
        new_parent[t] = parent if parent is not None else df.at[_row_ix(df, t), "manager_id"]
    for t in targets:
        rows = _children_rows(df, t)
        rows = [r for r in rows if df.at[r, "node_id"] not in targets]
        _set_manager(df, rows, new_parent[t])
        moved += len(rows)
    df = df[~(df["node_id"].isin(targets) & ~df["is_duplicate_id"])]
    scope = f" في إدارة {department}" if department else ""
    return df, [f"إزالة الطبقة الإدارية Job Level {job_level}{scope}: حذف {len(targets)} وظيفة "
                f"إشرافية ونقل {moved} سجل إلى المدير الأعلى التالي."]


def move_employee(df: pd.DataFrame, model: OrgModel, employee_id: str, new_manager_id: str,
                  move_department: bool = True) -> tuple[pd.DataFrame, list[str]]:
    if employee_id == new_manager_id:
        raise SimulationError("لا يمكن أن يكون الموظف مديرًا لنفسه.")
    e_ix = _row_ix(df, employee_id)
    m_ix = _row_ix(df, new_manager_id)
    if not (df.at[m_ix, "is_active"] or df.at[m_ix, "is_vacant"]):
        raise SimulationError("المدير الجديد ليس موظفًا نشطًا.")
    if new_manager_id in set(model.subtree_ids(employee_id, include_root=False, include_vacant=True)):
        raise SimulationError("المدير الجديد يتبع هذا الموظف (مباشرة أو غير مباشرة)؛ "
                              "النقل سينشئ علاقة دائرية.")
    df = df.copy()
    old = df.at[e_ix, "manager_id"]
    _set_manager(df, [e_ix], new_manager_id)
    msg = f"نقل {employee_id} من المدير {old or '—'} إلى المدير {new_manager_id}"
    if move_department:
        for col in ("department", "division", "business_unit"):
            df.at[e_ix, col] = df.at[m_ix, col]
        msg += f" (والإدارة إلى {df.at[m_ix, 'department']})"
    return df, [msg + "."]


def remove_manager(df: pd.DataFrame, model: OrgModel, manager_id: str,
                   reassign_to: str = "manager_of_removed") -> tuple[pd.DataFrame, list[str]]:
    t_ix = _row_ix(df, manager_id)
    if manager_id == model.ceo_id:
        raise SimulationError("لا يمكن حذف الـCEO في هذا السيناريو.")
    df = df.copy()
    rows = list(_children_rows(df, manager_id))
    parent = df.at[t_ix, "manager_id"]
    directs = set(df.loc[rows, "node_id"])
    log = []
    if reassign_to == "manager_of_removed":
        target = parent
        if not target:
            raise SimulationError("المدير المحذوف ليس له مدير أعلى؛ اختر مستلمًا آخر.")
    elif reassign_to == "department_head":
        dept = df.at[t_ix, "department"]
        target = department_heads(model).get(dept)
        if target in (None, manager_id):
            target = parent
            log.append("المدير المحذوف هو رئيس الإدارة؛ تم تحويل الفريق إلى مديره الأعلى.")
    else:
        target = reassign_to
        _row_ix(df, target)
        subtree = set(model.subtree_ids(manager_id, include_root=False, include_vacant=True))
        if target in subtree and target not in directs:
            raise SimulationError("المستلم يقع في مستوى أدنى داخل فريق المدير المحذوف؛ اختر مديرًا "
                                  "من خارج الفريق أو أحد الموظفين المباشرين (ترقية).")
    if target in directs:  # promote a direct report
        p_ix = _row_ix(df, target)
        _set_manager(df, [p_ix], parent)
        rows = [r for r in rows if r != p_ix]
        log.append(f"ترقية {target} ليحل محل {manager_id} ويتبع {parent or '—'}.")
    _set_manager(df, rows, target)
    df = df.drop(index=t_ix)
    log.append(f"حذف المدير {manager_id} ونقل {len(rows)} سجل إلى {target}.")
    return df, log


ACTIONS = {
    "merge_departments": lambda df, m, a: merge_departments(
        df, m, a["departments"], a.get("new_name", ""), a.get("consolidate_heads", False),
        a.get("primary_head")),
    "remove_layer": lambda df, m, a: remove_layer(df, m, int(a["job_level"]), a.get("department")),
    "move_employee": lambda df, m, a: move_employee(
        df, m, a["employee_id"], a["new_manager_id"], a.get("move_department", True)),
    "remove_manager": lambda df, m, a: remove_manager(
        df, m, a["manager_id"], a.get("reassign_to", "manager_of_removed")),
}


def apply_scenario(df_norm: pd.DataFrame, actions: list[dict],
                   base_model: OrgModel | None = None) -> ScenarioResult:
    """Apply actions sequentially to a copy of ``df_norm``."""
    df = df_norm.copy()
    model = base_model or build_org_model(df)
    log: list[str] = []
    for i, action in enumerate(actions, 1):
        fn = ACTIONS.get(action.get("type"))
        if fn is None:
            raise SimulationError(f"نوع إجراء غير معروف: {action.get('type')}")
        df, msgs = fn(df, model, action)
        log.extend(f"[{i}] {m}" for m in msgs)
        model = build_org_model(df)
    return ScenarioResult(df=df, model=model, log=log)


# ============================================================================ comparison
def org_summary(model: OrgModel, settings: Settings) -> dict:
    df = model.df
    act = df[df["is_active"]]
    mgr = act[act["is_manager"]]["direct_reports"]
    depth = act.loc[act["node_id"].ne(model.ceo_id), "depth"].dropna()
    return {
        "Employees": len(act),
        "Managers": len(mgr),
        "Management Ratio": safe_div(len(mgr), len(act)),
        "Layers": layer_count(df),
        "Max Depth": int(depth.max()) if len(depth) else np.nan,
        "Avg Depth": float(depth.mean()) if len(depth) else np.nan,
        "Avg Span": float(mgr.mean()) if len(mgr) else np.nan,
        "Median Span": float(mgr.median()) if len(mgr) else np.nan,
        "Low Span Managers": int((mgr <= settings.low_span_threshold).sum()),
        "High Span Managers": int((mgr > settings.high_span_threshold).sum()),
        "Invalid Reporting": int(act["reporting_status"].isin(INVALID_REPORTING_STATUSES).sum()),
        "Vacancies": int((df["is_vacant"] & ~df["is_duplicate_id"]).sum()),
        "Departments": int(act["department"].replace("", np.nan).nunique()),
    }


def _fmt(metric: str, v) -> str:
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return "—"
    if metric == "Management Ratio":
        return f"{v * 100:.1f}%"
    if isinstance(v, float) and not float(v).is_integer():
        return f"{v:.2f}"
    return f"{int(v):,}"


def compare(before: OrgModel, after: OrgModel, settings: Settings) -> dict:
    """Before/After comparison with an itemised list of what changed."""
    sb, sa = org_summary(before, settings), org_summary(after, settings)
    summary = pd.DataFrame({"Metric": list(sb), "Before": [sb[k] for k in sb],
                            "After": [sa[k] for k in sb]})
    summary["Change"] = [(a - b) if isinstance(a, (int, float)) and isinstance(b, (int, float))
                         else np.nan for a, b in zip(summary["After"], summary["Before"])]
    summary["Before (fmt)"] = [_fmt(m, v) for m, v in zip(summary["Metric"], summary["Before"])]
    summary["After (fmt)"] = [_fmt(m, v) for m, v in zip(summary["Metric"], summary["After"])]

    # Managers whose span changed (including removed / new managers)
    b = before.df[before.df["is_active"]].set_index("node_id")
    a = after.df[after.df["is_active"]].set_index("node_id")
    b = b[~b.index.duplicated()]
    a = a[~a.index.duplicated()]
    ids = sorted(set(b.index[b["is_manager"]]) | set(a.index[a["is_manager"]]))
    spans = pd.DataFrame(index=pd.Index(ids, name="node_id"))
    spans["employee_name"] = b["employee_name"].reindex(ids).fillna(a["employee_name"].reindex(ids))
    spans["job_title"] = b["job_title"].reindex(ids).fillna(a["job_title"].reindex(ids))
    spans["department_before"] = b["department"].reindex(ids)
    spans["span_before"] = b["direct_reports"].reindex(ids)
    spans["span_after"] = a["direct_reports"].reindex(ids)
    spans["status"] = np.where(spans["span_after"].isna(), "Removed",
                               np.where(spans["span_before"].isna(), "New", "Changed"))
    spans = spans[spans["span_before"].fillna(-1) != spans["span_after"].fillna(-1)].reset_index()

    # Employees whose depth changed
    common = b.index.intersection(a.index)
    db, da = b.loc[common, "depth"], a.loc[common, "depth"]
    changed = (db.fillna(-1) != da.fillna(-1))
    depth_changes = pd.DataFrame({
        "node_id": common[changed], "employee_name": b.loc[common[changed], "employee_name"].values,
        "department": a.loc[common[changed], "department"].values,
        "depth_before": db[changed].values, "depth_after": da[changed].values})

    # Department metrics
    ub = unit_metrics(before.df, "department", settings).set_index("department")
    ua = unit_metrics(after.df, "department", settings).set_index("department")
    cols = ["headcount", "managers", "management_ratio", "avg_span", "layers", "vacancies"]
    depts = ub.index.union(ua.index)
    dcomp = pd.concat({"before": ub[cols].reindex(depts), "after": ua[cols].reindex(depts)}, axis=1)
    diff_mask = pd.Series(False, index=depts)
    for c in cols:
        diff_mask |= dcomp[("before", c)].fillna(-1).round(4) != dcomp[("after", c)].fillna(-1).round(4)
    dept_changes = dcomp[diff_mask]
    dept_changes.columns = [f"{c}_{w}" for w, c in dept_changes.columns]
    dept_changes = dept_changes[[f"{c}_{w}" for c in cols for w in ("before", "after")]].reset_index()

    # Narrative
    lines = []
    for k in sb:
        if _fmt(k, sb[k]) != _fmt(k, sa[k]):
            lines.append(f"{k}: {_fmt(k, sb[k])} → {_fmt(k, sa[k])}")
    for r in spans.head(25).itertuples():
        bef = "—" if pd.isna(r.span_before) else int(r.span_before)
        aft = "removed" if pd.isna(r.span_after) else int(r.span_after)
        lines.append(f"Manager {r.node_id} ({r.job_title}): Direct Reports {bef} → {aft}")
    for r in dept_changes.head(25).itertuples():
        parts = []
        for c, label in [("headcount", "Headcount"), ("managers", "Managers"),
                         ("layers", "Layers"), ("management_ratio", "Management Ratio")]:
            bv, av = getattr(r, f"{c}_before"), getattr(r, f"{c}_after")
            if _fmt("Management Ratio" if c == "management_ratio" else c, bv) != \
                    _fmt("Management Ratio" if c == "management_ratio" else c, av):
                fmt = (lambda v: _fmt("Management Ratio", v)) if c == "management_ratio" \
                    else (lambda v: _fmt(c, v))
                parts.append(f"{label} {fmt(bv)} → {fmt(av)}")
        if parts:
            lines.append(f"Department {r.department}: " + "; ".join(parts))
    if len(depth_changes):
        lines.append(f"Organizational Depth تغير لـ {len(depth_changes)} موظف/موظفين.")
    return {"summary": summary, "span_changes": spans, "depth_changes": depth_changes,
            "department_changes": dept_changes, "narrative": lines,
            "before": sb, "after": sa}
