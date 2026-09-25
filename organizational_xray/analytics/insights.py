""""X-Ray answers": the key structural questions answered from the data.

Each answer carries the numbers it is based on, so the dashboard never states
a conclusion the dataset does not support.
"""
from __future__ import annotations

import pandas as pd

from analytics.departments import unit_metrics
from analytics.hierarchy import OrgModel, layer_count
from utils.config import (
    RS_CIRCULAR,
    RS_DISCONNECTED,
    RS_INVALID,
    RS_MISSING,
    RS_TERMINATED,
    Settings,
)
from utils.helpers import pct


def key_questions(model: OrgModel, df: pd.DataFrame, findings: pd.DataFrame,
                  settings: Settings) -> list[dict]:
    """``df`` is the (possibly filtered) enriched dataset."""
    act = df[df["is_active"]]
    mgr = act[act["is_manager"]]
    units = unit_metrics(df, "department", settings)
    units = units[units["headcount"] > 0]
    out: list[dict] = []

    def q(question, answer, evidence="", page=""):
        out.append({"question": question, "answer": answer, "evidence": evidence, "page": page})

    d = act["depth"].dropna()
    q("كم عدد الطبقات الإدارية؟",
      f"{layer_count(df)} طبقات هيكلية" if len(d) else "لا يمكن الحساب (لا يوجد CEO)",
      f"العمق من {int(d.min())} إلى {int(d.max())} علاقة إدارية حتى الـCEO." if len(d) else "",
      "Layers")
    q("كم عدد المديرين؟", f"{len(mgr):,} مدير",
      f"Management Ratio = {pct(len(mgr) / len(act) if len(act) else float('nan'))} "
      f"من {len(act):,} موظف نشط.", "Span of Control")
    if len(mgr):
        q("كم عدد الموظفين تحت كل مدير؟",
          f"الوسيط {mgr['direct_reports'].median():g} والمتوسط {mgr['direct_reports'].mean():.1f}",
          f"النطاق من {int(mgr['direct_reports'].min())} إلى {int(mgr['direct_reports'].max())} موظف مباشر.",
          "Span of Control")
    low = units.sort_values("low_span_managers", ascending=False)
    low = low[low["low_span_managers"] > 0].head(3)
    q("أين توجد الإدارات ذات Span of Control منخفض؟",
      ", ".join(f"{r.department} ({r.low_span_managers})" for r in low.itertuples()) or "لا توجد",
      f"عدد المديرين الذين لديهم ≤ {settings.low_span_threshold} موظفين مباشرين في كل إدارة.",
      "Departments")
    high = units.sort_values("high_span_managers", ascending=False)
    high = high[high["high_span_managers"] > 0].head(3)
    q("أين توجد الإدارات ذات Span of Control مرتفع؟",
      ", ".join(f"{r.department} ({r.high_span_managers})" for r in high.itertuples()) or "لا توجد",
      f"عدد المديرين الذين لديهم > {settings.high_span_threshold} موظفًا مباشرًا.", "Departments")
    if len(d):
        deepest = act.loc[act["depth"].idxmax()]
        q("ما أطول سلسلة إدارية؟", f"{int(deepest['depth'])} علاقات إدارية",
          f"مثال: {deepest['node_id']} – {deepest['job_title']} ({deepest['department']}).", "Layers")
    rs = act["reporting_status"].value_counts()
    q("هل توجد موظفون بدون مدير؟",
      f"{int(rs.get(RS_MISSING, 0))} بدون Manager ID، {int(rs.get(RS_INVALID, 0))} بمدير غير موجود",
      f"بالإضافة إلى {int(rs.get(RS_DISCONNECTED, 0))} موظف لا تصل سلسلتهم إلى الـCEO بسبب انقطاع أعلى.",
      "X-Ray Findings")
    term_mgrs = act.loc[act["reporting_status"].eq(RS_TERMINATED), "manager_id"].nunique()
    q("هل توجد علاقات إدارية تشير إلى مدير منتهي الخدمة؟",
      f"{int(rs.get(RS_TERMINATED, 0))} موظف يتبعون {term_mgrs} مدير/مديرين منتهي الخدمة",
      "Manager ID يشير إلى سجل حالته Terminated.", "X-Ray Findings")
    q("هل توجد حلقات إدارية Circular Reporting؟",
      f"{len(model.cycles)} حلقة ({int(rs.get(RS_CIRCULAR, 0))} موظف)",
      " | ".join(" → ".join(c + [c[0]]) for c in model.cycles[:3]), "X-Ray Findings")
    small = units[units["headcount"] <= settings.small_department_threshold]
    q("هل توجد إدارات صغيرة جدًا؟",
      ", ".join(f"{r.department} ({r.headcount})" for r in small.itertuples()) or "لا توجد",
      f"Headcount ≤ {settings.small_department_threshold}.", "Departments")
    hm = units[(units["headcount"] > settings.small_department_threshold)
               & (units["management_ratio"] > settings.high_management_ratio)]
    q("هل نسبة المديرين مرتفعة في بعض الإدارات؟",
      ", ".join(f"{r.department} ({pct(r.management_ratio)})"
                for r in hm.sort_values("management_ratio", ascending=False).itertuples())
      or "لا توجد",
      f"Management Ratio > {pct(settings.high_management_ratio, 0)}.", "Departments")
    dup = findings[findings["type"].eq("DUPLICATE_POSITION")] if not findings.empty else findings
    q("هل توجد وظائف متكررة أو متشابهة؟",
      f"{len(dup)} ملاحظة" if len(dup) else "لا توجد",
      "Position IDs مكررة، صيغ كتابة مختلفة لنفس المسمى، ومسميات متشابهة نصيًا.", "X-Ray Findings")
    vac = df[df["is_vacant"] & ~df["is_duplicate_id"]]
    top_vac = vac["department"].replace("", "(Unassigned)").value_counts().head(3)
    q("أين توجد شواغر؟", f"{len(vac)} وظيفة شاغرة",
      ", ".join(f"{k} ({v})" for k, v in top_vac.items()), "Departments")
    return out
