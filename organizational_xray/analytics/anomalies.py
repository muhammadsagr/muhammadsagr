"""X-Ray Findings engine.

Each detector is a pure function of the enriched model + settings and returns
explainable findings: the rule that fired, the measured value, the configured
threshold, an organisational benchmark and the IDs of every record involved.

Wording principle: a finding describes *what the data shows* and asks for a
review. It never concludes that a role or person is unnecessary.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, field

import numpy as np
import pandas as pd

from analytics.departments import duplicate_position_ids, job_title_analysis, unit_metrics
from analytics.hierarchy import OrgModel
from utils.config import (
    FINDING_TYPES,
    RS_CIRCULAR,
    RS_INVALID,
    RS_MISSING,
    RS_TERMINATED,
    SEVERITY_RANK,
    Settings,
)
from utils.helpers import pct

FINDING_COLUMNS = [
    "finding_id", "type", "severity", "entity_type", "entity_id", "entity_name", "department",
    "description", "evidence", "recommended_investigation", "rule", "metric", "value",
    "threshold", "benchmark", "related_ids",
]

TYPE_LABELS_AR = {
    "LOW_SPAN_OF_CONTROL": "Span of Control منخفض",
    "HIGH_SPAN_OF_CONTROL": "Span of Control مرتفع",
    "DEEP_HIERARCHY": "تسلسل إداري عميق",
    "ORPHAN_EMPLOYEE": "موظف بدون مدير",
    "INVALID_MANAGER": "مدير غير موجود",
    "TERMINATED_MANAGER": "مدير منتهي الخدمة",
    "CIRCULAR_REPORTING": "علاقة إدارية دائرية",
    "SMALL_DEPARTMENT": "وحدة تنظيمية صغيرة",
    "HIGH_MANAGEMENT_RATIO": "نسبة مديرين مرتفعة",
    "VACANT_POSITION": "وظيفة شاغرة",
    "DUPLICATE_POSITION": "وظائف مكررة / متشابهة",
}


@dataclass
class Finding:
    type: str
    severity: str
    entity_type: str
    entity_id: str
    entity_name: str
    department: str
    description: str
    evidence: str
    recommended_investigation: str
    rule: str
    metric: str
    value: object
    threshold: object = None
    benchmark: str = ""
    related_ids: list[str] = field(default_factory=list)
    finding_id: str = ""


def _name(row) -> str:
    return f"{row['employee_name']} ({row['job_title']})" if row["employee_name"] else row["node_id"]


def _lvl(v) -> str:
    return "—" if pd.isna(v) else str(int(v))


# ============================================================================ detectors
def detect_span(model: OrgModel, s: Settings) -> list[Finding]:
    df = model.df
    mgrs = df[df["is_manager"]]
    if mgrs.empty:
        return []
    median = float(mgrs["direct_reports"].median())
    # Loop members are reported as CIRCULAR_REPORTING; their "spans" are artefacts.
    scope = mgrs[mgrs["reporting_status"].ne(RS_CIRCULAR)]
    if s.exclude_executives_from_span:
        scope = scope[~scope["job_level"].isin([0, 1])]
    out: list[Finding] = []
    for _, r in scope.iterrows():
        n = int(r["direct_reports"])
        common = (f"الوسيط التنظيمي لـSpan of Control = {median:g}. "
                  f"إجمالي التابعين (مباشر وغير مباشر) = {int(r['total_reports'])}. "
                  f"وظائف شاغرة تابعة مباشرة = {int(r['vacant_direct_positions'])}. "
                  f"Job Level = {_lvl(r['job_level'])}.")
        if n <= s.low_span_threshold:
            out.append(Finding(
                type="LOW_SPAN_OF_CONTROL",
                severity="Attention" if n == 1 else "Informational",
                entity_type="Manager", entity_id=r["node_id"], entity_name=_name(r),
                department=r["department"],
                description=(f"تم اكتشاف Span of Control منخفض ويحتاج إلى مراجعة: لدى هذا المدير "
                             f"{n} موظف/موظفين مباشرين، مقارنة بالحد المحدد حاليًا وهو "
                             f"{s.low_span_threshold}."),
                evidence=f"عدد الموظفين المباشرين النشطين = {n}. " + common,
                recommended_investigation=(
                    "مراجعة سبب محدودية نطاق الإشراف: هل الدور تخصصي أو قيادي فني؟ هل توجد وظائف "
                    "شاغرة ستُشغل قريبًا؟ هل يمكن دمج الفريق مع فريق مجاور؟ النتيجة لا تعني أن الدور "
                    "غير ضروري."),
                rule=f"direct_reports <= Low Span Threshold ({s.low_span_threshold})",
                metric="Direct Reports", value=n, threshold=s.low_span_threshold,
                benchmark=f"Organizational median = {median:g}",
                related_ids=[r["node_id"]] + model.direct_report_ids(r["node_id"])))
        elif n > s.high_span_threshold:
            ratio = n / s.high_span_threshold
            sev = "Attention" if ratio <= 1.5 else ("Significant" if ratio <= 2.5 else "Critical")
            out.append(Finding(
                type="HIGH_SPAN_OF_CONTROL", severity=sev,
                entity_type="Manager", entity_id=r["node_id"], entity_name=_name(r),
                department=r["department"],
                description=(f"تم اكتشاف Span of Control مرتفع: لدى هذا المدير {n} موظفًا مباشرًا "
                             f"مقارنة بالحد المحدد حاليًا وهو {s.high_span_threshold} "
                             f"وبوسيط تنظيمي يبلغ {median:g}."),
                evidence=(f"هذا المدير لديه {n} موظفًا مباشرًا مقارنة بوسيط تنظيمي يبلغ {median:g} "
                          f"(أي {n / median:.1f}× الوسيط). " + common) if median else common,
                recommended_investigation=(
                    "مراجعة طبيعة العمل (عمل متجانس/تشغيلي قد يتحمل نطاقًا أوسع)، وجود قادة فرق "
                    "غير رسميين، وعبء الإشراف والتقييم على المدير."),
                rule=f"direct_reports > High Span Threshold ({s.high_span_threshold})",
                metric="Direct Reports", value=n, threshold=s.high_span_threshold,
                benchmark=f"Organizational median = {median:g}",
                related_ids=[r["node_id"]] + model.direct_report_ids(r["node_id"])))
    return out


def detect_deep_hierarchy(model: OrgModel, s: Settings) -> list[Finding]:
    df = model.df
    act = df[df["is_active"] & df["depth"].notna()]
    if act.empty:
        return []
    org_median = float(act["depth"].median())
    org_max = int(act["depth"].max())
    titles = dict(zip(df["node_id"], df["job_title"]))
    out = []
    for dept, grp in act.groupby("department"):
        deep = grp[grp["depth"] > s.deep_hierarchy_threshold]
        if deep.empty:
            continue
        max_d = int(grp["depth"].max())
        deepest = grp.sort_values(["depth", "node_id"], ascending=[False, True]).iloc[0]
        chain = list(reversed(model.chain_up(deepest["node_id"])))
        chain_txt = " → ".join(titles.get(n, n) or n for n in chain)
        excess = max_d - s.deep_hierarchy_threshold
        out.append(Finding(
            type="DEEP_HIERARCHY", severity="Attention" if excess == 1 else "Significant",
            entity_type="Department", entity_id=dept or "(Unassigned)",
            entity_name=dept or "(Unassigned)", department=dept,
            description=(f"تم اكتشاف تسلسل إداري عميق (Deep Reporting Chain): أقصى عمق في الإدارة "
                         f"{max_d} علاقات إدارية حتى الـCEO، مقارنة بالحد المحدد {s.deep_hierarchy_threshold}."),
            evidence=(f"{len(deep)} موظف/موظفين على عمق أكبر من {s.deep_hierarchy_threshold}. "
                      f"عدد الطبقات في الإدارة = {grp['depth'].nunique()}. "
                      f"الوسيط التنظيمي للعمق = {org_median:g}، والحد الأقصى على مستوى المنظمة = {org_max}. "
                      f"أطول سلسلة: {chain_txt}."),
            recommended_investigation=(
                "مراجعة ما إذا كانت كل طبقة تضيف نطاق مسؤولية مختلفًا، وهل توجد مسميات متتالية "
                "بنفس المستوى الوظيفي (مثل Senior Director ثم Director)، وأثر العمق على سرعة القرار."),
            rule=f"employee depth > Deep Hierarchy Threshold ({s.deep_hierarchy_threshold})",
            metric="Max Depth", value=max_d, threshold=s.deep_hierarchy_threshold,
            benchmark=f"Organizational median depth = {org_median:g}",
            related_ids=deep["node_id"].tolist()))
    return out


def detect_reporting(model: OrgModel, s: Settings) -> list[Finding]:
    df = model.df
    names = dict(zip(df["node_id"], df["employee_name"]))
    out = []
    for _, r in df[df["reporting_status"].eq(RS_MISSING)].iterrows():
        out.append(Finding(
            type="ORPHAN_EMPLOYEE", severity="Significant", entity_type="Employee",
            entity_id=r["node_id"], entity_name=_name(r), department=r["department"],
            description="موظف بدون Manager ID وليس هو الـCEO (Invalid Reporting Relationship).",
            evidence=(f"Manager ID فارغ. الـCEO المحدد في البيانات = {model.ceo_id}. "
                      f"عدد التابعين لهذا الموظف = {int(r['total_reports'])}. "
                      f"رقم السجل في الملف = {r['row_number']}."),
            recommended_investigation="التحقق من المدير المباشر الفعلي وتحديث Manager ID في نظام الموارد البشرية.",
            rule="manager_id is blank AND employee is not the CEO",
            metric="Manager ID", value="(blank)", related_ids=[r["node_id"]]))
    for _, r in df[df["reporting_status"].eq(RS_INVALID)].iterrows():
        out.append(Finding(
            type="INVALID_MANAGER", severity="Significant", entity_type="Employee",
            entity_id=r["node_id"], entity_name=_name(r), department=r["department"],
            description=f"Manager ID ({r['manager_id']}) غير موجود في البيانات (Invalid Reporting Relationship).",
            evidence=(f"Manager ID = {r['manager_id']}، Manager Name المسجل = "
                      f"'{r['manager_name'] or '—'}'. لا يوجد أي سجل بهذا الرقم. "
                      f"رقم السجل في الملف = {r['row_number']}."),
            recommended_investigation="التحقق من صحة رقم المدير (خطأ إدخال، مدير لم يُنقل للنظام، أو رقم قديم).",
            rule="manager_id not found among Employee IDs",
            metric="Manager ID", value=r["manager_id"], related_ids=[r["node_id"]]))
    term = df[df["reporting_status"].eq(RS_TERMINATED)]
    for mid, grp in term.groupby("manager_id"):
        mrow = df[df["node_id"].eq(mid)].iloc[0]
        out.append(Finding(
            type="TERMINATED_MANAGER", severity="Significant", entity_type="Manager",
            entity_id=mid, entity_name=_name(mrow), department=mrow["department"],
            description=(f"{len(grp)} موظف/موظفين ما زالوا يتبعون مديرًا حالته الوظيفية "
                         f"'{mrow['employment_status']}' (Invalid Reporting Relationship)."),
            evidence=(f"المدير {mid} – {names.get(mid, '')}: Employment Status = "
                      f"{mrow['employment_status']}، Position Status = {mrow['position_status']}. "
                      f"الموظفون المتأثرون: {', '.join(grp['node_id'].head(15))}"
                      f"{' …' if len(grp) > 15 else ''}."),
            recommended_investigation=("تحديد المدير البديل أو المكلف، وتحديث Manager ID للموظفين، "
                                       "ومراجعة حالة الوظيفة (قد تكون شاغرة فعليًا)."),
            rule="manager record exists but Employment Status is not Active / On Leave",
            metric="Affected employees", value=len(grp),
            related_ids=[mid] + grp["node_id"].tolist()))
    return out


def detect_cycles(model: OrgModel, s: Settings) -> list[Finding]:
    df = model.df
    names = dict(zip(df["node_id"], df["employee_name"]))
    depts = dict(zip(df["node_id"], df["department"]))
    out = []
    for cyc in model.cycles:
        path = " → ".join(f"{n} ({names.get(n, '')})" for n in cyc + [cyc[0]])
        downstream = set()
        for n in cyc:
            downstream |= set(model.subtree_ids(n, include_root=False))
        downstream -= set(cyc)
        out.append(Finding(
            type="CIRCULAR_REPORTING", severity="Critical", entity_type="Reporting Loop",
            entity_id=" → ".join(cyc), entity_name=f"{len(cyc)}-employee loop",
            department=depts.get(cyc[0], ""),
            description=("تم اكتشاف علاقة إدارية دائرية: سلسلة المديرين تعود إلى نفس الموظف ولا تصل "
                         "إلى الـCEO." if len(cyc) > 1 else
                         "موظف مسجل كمدير لنفسه (Manager ID = Employee ID)."),
            evidence=(f"المسار: {path}. عدد الموظفين خارج الحلقة المتأثرين (لا يصلون إلى الـCEO) = "
                      f"{len(downstream)}."),
            recommended_investigation="تصحيح Manager ID لأحد أعضاء الحلقة على الأقل بحيث تصل السلسلة إلى الـCEO.",
            rule="strongly connected component (size > 1) or self-loop in the reporting graph",
            metric="Loop length", value=len(cyc), related_ids=list(cyc) + sorted(downstream)))
    return out


def detect_units(model: OrgModel, s: Settings) -> list[Finding]:
    df = model.df
    units = unit_metrics(df, "department", s)
    act = df[df["is_active"]]
    org_ratio = act["is_manager"].sum() / len(act) if len(act) else np.nan
    median_hc = float(units["headcount"].median()) if not units.empty else np.nan
    out = []
    for _, u in units.iterrows():
        dept = u["department"]
        members = df[(df["department"].eq(dept) | ((dept == "(Unassigned)") & df["department"].eq("")))
                     & (df["is_active"] | df["is_vacant"])]["node_id"].tolist()
        hc = int(u["headcount"])
        if hc <= s.small_department_threshold:
            out.append(Finding(
                type="SMALL_DEPARTMENT", severity="Attention" if hc == 0 else "Informational",
                entity_type="Department", entity_id=dept, entity_name=dept, department=dept,
                description=(f"Small Organizational Unit: عدد الموظفين النشطين في الإدارة = {hc}، "
                             f"مقارنة بالحد المحدد {s.small_department_threshold}."),
                evidence=(f"Headcount = {hc}، الوظائف الشاغرة = {int(u['vacancies'])}، "
                          f"عدد المديرين = {int(u['managers'])}. وسيط حجم الإدارات = {median_hc:g}."),
                recommended_investigation=("مراجعة ما إذا كانت الوحدة وظيفة متخصصة مستقلة بطبيعتها، أو "
                                           "قيد التأسيس، أو يمكن ضمها لوحدة ذات صلة."),
                rule=f"department headcount <= Small Department Threshold ({s.small_department_threshold})",
                metric="Headcount", value=hc, threshold=s.small_department_threshold,
                benchmark=f"Median department headcount = {median_hc:g}", related_ids=members))
        ratio = u["management_ratio"]
        if hc > s.small_department_threshold and pd.notna(ratio) and ratio > s.high_management_ratio:
            out.append(Finding(
                type="HIGH_MANAGEMENT_RATIO",
                severity="Attention" if ratio <= 2 * s.high_management_ratio else "Significant",
                entity_type="Department", entity_id=dept, entity_name=dept, department=dept,
                description=(f"نسبة المديرين في الإدارة {pct(ratio)} مقارنة بالحد المحدد "
                             f"{pct(s.high_management_ratio)}."),
                evidence=(f"Management Ratio = {int(u['managers'])} مدير ÷ {hc} موظف = {pct(ratio)}. "
                          f"النسبة على مستوى المنظمة = {pct(org_ratio)}. متوسط Span of Control في "
                          f"الإدارة = {u['avg_span']:.2f}. عدد الطبقات = {int(u['layers'])}."),
                recommended_investigation=("مراجعة عدد المستويات الإشرافية مقارنة بحجم الفريق، ووجود "
                                           "مديرين بفرق صغيرة جدًا، وإمكانية تبسيط الهيكل."),
                rule=f"managers / headcount > High Management Ratio ({pct(s.high_management_ratio, 0)})",
                metric="Management Ratio", value=round(float(ratio), 4),
                threshold=s.high_management_ratio,
                benchmark=f"Organization ratio = {pct(org_ratio)}", related_ids=members))
    return out


def detect_vacancies(model: OrgModel, s: Settings) -> list[Finding]:
    df = model.df
    out = []
    for _, r in df[df["is_vacant"] & ~df["is_duplicate_id"]].iterrows():
        lvl = r["job_level"]
        has_reports = int(r["direct_reports"]) + int(r["vacant_direct_positions"])
        managerial = pd.notna(lvl) and lvl <= 4
        sev = "Attention" if (managerial or has_reports) else "Informational"
        out.append(Finding(
            type="VACANT_POSITION", severity=sev, entity_type="Position",
            entity_id=r["position_id"] or r["node_id"], entity_name=r["job_title"] or "(no title)",
            department=r["department"],
            description=f"وظيفة شاغرة (Position Status = Vacant): {r['job_title']}.",
            evidence=(f"Position ID = {r['position_id']}، Job Level = {_lvl(lvl)}، تتبع المدير "
                      f"{r['manager_id'] or '—'}. وظائف تابعة لهذه الوظيفة = {has_reports}."),
            recommended_investigation=("التحقق من حالة التوظيف لهذه الوظيفة ومدة شغورها، وأثرها على "
                                       "الفريق." + (" الوظيفة ذات مستوى إشرافي." if managerial else "")),
            rule="position_status == 'Vacant'", metric="Position Status", value="Vacant",
            related_ids=[r["node_id"]]))
    # Manager-level roles whose entire team is vacant (0 active direct reports)
    empty = df[df["is_active"] & df["direct_reports"].eq(0) & df["vacant_direct_positions"].gt(0)]
    for _, r in empty.iterrows():
        out.append(Finding(
            type="VACANT_POSITION", severity="Attention", entity_type="Manager",
            entity_id=r["node_id"], entity_name=_name(r), department=r["department"],
            description=(f"مدير بدون موظفين نشطين: جميع الوظائف التابعة له ({int(r['vacant_direct_positions'])}) شاغرة."),
            evidence=(f"Direct Reports النشطون = 0، الوظائف الشاغرة التابعة = "
                      f"{int(r['vacant_direct_positions'])}، Job Level = {_lvl(r['job_level'])}."),
            recommended_investigation="مراجعة خطة شغل الفريق أو ما إذا كان الفريق قد نُقل/أُعيد تنظيمه.",
            rule="active employee with 0 active and >= 1 vacant direct positions",
            metric="Vacant direct positions", value=int(r["vacant_direct_positions"]),
            related_ids=[r["node_id"]] + model.direct_report_ids(r["node_id"], include_vacant=True)))
    return out


def detect_duplicates(model: OrgModel, s: Settings) -> list[Finding]:
    df = model.df
    out = []
    dups = duplicate_position_ids(df)
    for pid, grp in dups.groupby("position_id"):
        out.append(Finding(
            type="DUPLICATE_POSITION", severity="Significant", entity_type="Position",
            entity_id=pid, entity_name=", ".join(grp["job_title"].unique()),
            department=grp["department"].iloc[0],
            description=f"Position ID {pid} مسجل لأكثر من سجل ({len(grp)} سجلات).",
            evidence="السجلات: " + "; ".join(f"{r.node_id} – {r.employee_name} (row {r.row_number})"
                                             for r in grp.itertuples()),
            recommended_investigation="التحقق من أن كل موظف مرتبط بوظيفة مستقلة في هيكل الوظائف.",
            rule="position_id appears on more than one record", metric="Records", value=len(grp),
            related_ids=grp["node_id"].tolist()))
    jt = job_title_analysis(df, s)
    for v in jt["variants"].itertuples():
        titles = v.variants.split(" | ")
        ids = df[df["job_title"].isin(titles) & (df["is_active"] | df["is_vacant"])]["node_id"].tolist()
        out.append(Finding(
            type="DUPLICATE_POSITION", severity="Attention", entity_type="Job Title",
            entity_id=v.normalized_title, entity_name=v.variants, department=v.departments,
            description="مسمى وظيفي مكرر بصيغ كتابة مختلفة (Duplicate Job Title).",
            evidence=f"الصيغ: {v.variants}. عدد الوظائف = {v.positions}. الإدارات: {v.departments}.",
            recommended_investigation="توحيد المسمى في دليل الوظائف (Job Catalogue).",
            rule="job titles identical after normalising case / spacing / punctuation",
            metric="Variants", value=len(titles), related_ids=ids))
    for p in jt["similar"].itertuples():
        ids = df[df["job_title"].isin([p.title_a, p.title_b])
                 & (df["is_active"] | df["is_vacant"])]["node_id"].tolist()
        out.append(Finding(
            type="DUPLICATE_POSITION", severity="Informational", entity_type="Job Title",
            entity_id=f"{p.title_a} ~ {p.title_b}", entity_name=f"{p.title_a} ~ {p.title_b}",
            department=", ".join(sorted({*p.departments_a.split(", "), *p.departments_b.split(", ")} - {""})),
            description="مسميات وظيفية متشابهة نصيًا (Similar Job Titles) قد تشير إلى تداخل أدوار.",
            evidence=(f"'{p.title_a}' ({p.positions_a} وظيفة؛ {p.departments_a}) و'{p.title_b}' "
                      f"({p.positions_b} وظيفة؛ {p.departments_b}). درجة التشابه = {p.similarity:.2f}."),
            recommended_investigation="مقارنة الوصف الوظيفي للمسميين لتحديد ما إذا كانا دورًا واحدًا أم دورين مختلفين.",
            rule=f"text similarity >= {s.title_similarity_threshold}", metric="Similarity",
            value=p.similarity, threshold=s.title_similarity_threshold, related_ids=ids))
    return out


DETECTORS = [detect_cycles, detect_reporting, detect_span, detect_deep_hierarchy, detect_units,
             detect_duplicates, detect_vacancies]


# ============================================================================ public API
def detect_findings(model: OrgModel, settings: Settings | None = None) -> pd.DataFrame:
    """Run every detector. A failing detector never stops the others."""
    settings = settings or Settings()
    findings: list[Finding] = []
    errors = []
    for det in DETECTORS:
        try:
            findings.extend(det(model, settings))
        except Exception as exc:  # pragma: no cover - defensive
            errors.append(f"{det.__name__}: {exc}")
    type_rank = {t: i for i, t in enumerate(FINDING_TYPES)}
    findings.sort(key=lambda f: (SEVERITY_RANK[f.severity], type_rank.get(f.type, 99),
                                 str(f.department), str(f.entity_id)))
    for i, f in enumerate(findings, 1):
        f.finding_id = f"F-{i:04d}"
    out = pd.DataFrame([asdict(f) for f in findings], columns=FINDING_COLUMNS)
    out.attrs["errors"] = errors
    return out


def explain_finding(findings: pd.DataFrame, finding_id: str, model: OrgModel) -> dict:
    """Everything needed to justify a finding (rule, numbers, source records)."""
    row = findings[findings["finding_id"].eq(finding_id)]
    if row.empty:
        raise KeyError(finding_id)
    f = row.iloc[0].to_dict()
    ids = list(f["related_ids"])
    records = model.df[model.df["node_id"].isin(ids)]
    f["records"] = records
    return f


def filter_findings(findings: pd.DataFrame, node_ids: set[str], departments: set[str]
                    ) -> pd.DataFrame:
    """Keep findings touching the filtered population."""
    if findings.empty:
        return findings
    keep = findings.apply(
        lambda r: bool(set(r["related_ids"]) & node_ids)
        or (r["entity_type"] == "Department" and r["department"] in departments), axis=1)
    return findings[keep]


def summarize_findings(findings: pd.DataFrame) -> pd.DataFrame:
    if findings.empty:
        return pd.DataFrame(columns=["type", "severity", "count"])
    return findings.groupby(["type", "severity"]).size().reset_index(name="count")
