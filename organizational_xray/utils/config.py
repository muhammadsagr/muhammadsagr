"""Central configuration: canonical schema, labels and user-adjustable thresholds.

Nothing in the analytics layer hard-codes a threshold; every rule reads from a
``Settings`` instance so the UI (and a future AI assistant) can change them.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass, fields

# --------------------------------------------------------------------------- schema
# Canonical (internal) column names. Everything downstream uses these.
EMPLOYEE_ID = "employee_id"
EMPLOYEE_NAME = "employee_name"
MANAGER_ID = "manager_id"
MANAGER_NAME = "manager_name"

CANONICAL_COLUMNS: list[str] = [
    "employee_id",
    "employee_name",
    "gender",
    "age",
    "hire_date",
    "employment_status",
    "job_title",
    "job_level",
    "grade",
    "department",
    "division",
    "business_unit",
    "location",
    "manager_id",
    "manager_name",
    "salary",
    "position_id",
    "position_status",
    "employment_type",
    "work_arrangement",
    "performance_rating",
    "years_of_service",
]

# Columns required by the import contract (Section 29 of the spec).
IMPORT_REQUIRED_COLUMNS: list[str] = [
    "employee_id",
    "employee_name",
    "manager_id",
    "job_title",
    "department",
    "division",
    "business_unit",
    "job_level",
    "salary",
    "employment_status",
    "position_id",
    "position_status",
]
# Without these two the hierarchy cannot be built at all.
STRUCTURALLY_REQUIRED: list[str] = ["employee_id", "manager_id"]

STRING_COLUMNS = [
    "employee_id", "employee_name", "gender", "employment_status", "job_title", "grade",
    "department", "division", "business_unit", "location", "manager_id", "manager_name",
    "position_id", "position_status", "employment_type", "work_arrangement",
]
NUMERIC_COLUMNS = ["age", "job_level", "salary", "performance_rating", "years_of_service"]
DATE_COLUMNS = ["hire_date"]

# Display names for tables / exports.
DISPLAY_NAMES: dict[str, str] = {
    "employee_id": "Employee ID",
    "employee_name": "Name",
    "gender": "Gender",
    "age": "Age",
    "hire_date": "Hire Date",
    "employment_status": "Employment Status",
    "job_title": "Job Title",
    "job_level": "Job Level",
    "grade": "Grade",
    "department": "Department",
    "division": "Division",
    "business_unit": "Business Unit",
    "location": "Location",
    "manager_id": "Manager ID",
    "manager_name": "Manager Name",
    "salary": "Salary",
    "position_id": "Position ID",
    "position_status": "Position Status",
    "employment_type": "Employment Type",
    "work_arrangement": "Work Arrangement",
    "performance_rating": "Performance Rating",
    "years_of_service": "Years of Service",
    # derived
    "node_id": "Node ID",
    "depth": "Depth",
    "layer": "Layer",
    "reporting_status": "Reporting Status",
    "direct_reports": "Direct Reports",
    "vacant_direct_positions": "Vacant Direct Positions",
    "total_reports": "Total Reports",
    "is_manager": "Is Manager",
    "is_active": "Is Active",
    "is_vacant": "Is Vacant",
    "span_category": "Span Category",
}

# Allowed values (validation + normalisation)
EMPLOYMENT_STATUSES = ["Active", "On Leave", "Terminated"]
ACTIVE_STATUSES = {"Active", "On Leave"}
POSITION_STATUSES = ["Filled", "Vacant"]
EMPLOYMENT_TYPES = ["Full-Time", "Part-Time", "Contractor"]
WORK_ARRANGEMENTS = ["On-site", "Hybrid", "Remote"]

# Nominal names of the job levels (declared hierarchy, not measured depth).
LEVEL_NAMES: dict[int, str] = {
    0: "CEO",
    1: "C-Suite",
    2: "Directors",
    3: "Senior Managers",
    4: "Managers",
    5: "Supervisors",
    6: "Individual Contributors",
}

# Finding vocabulary --------------------------------------------------------------
SEVERITIES = ["Critical", "Significant", "Attention", "Informational"]
SEVERITY_RANK = {s: i for i, s in enumerate(SEVERITIES)}  # 0 = most severe

FINDING_TYPES = [
    "CIRCULAR_REPORTING",
    "ORPHAN_EMPLOYEE",
    "INVALID_MANAGER",
    "TERMINATED_MANAGER",
    "HIGH_SPAN_OF_CONTROL",
    "LOW_SPAN_OF_CONTROL",
    "DEEP_HIERARCHY",
    "HIGH_MANAGEMENT_RATIO",
    "SMALL_DEPARTMENT",
    "DUPLICATE_POSITION",
    "VACANT_POSITION",
]

# Reporting-status vocabulary (hierarchy engine)
RS_CEO = "Top of Hierarchy"
RS_VALID = "Valid"
RS_MISSING = "Missing Manager"
RS_INVALID = "Invalid Manager"
RS_TERMINATED = "Terminated Manager"
RS_CIRCULAR = "Circular Reporting"
RS_DISCONNECTED = "Disconnected (upstream break)"
RS_INACTIVE = "Not Active"
RS_VACANT = "Vacant Position"
RS_DUPLICATE = "Duplicate ID (excluded)"
INVALID_REPORTING_STATUSES = {RS_MISSING, RS_INVALID, RS_TERMINATED, RS_CIRCULAR}


# --------------------------------------------------------------------------- settings
@dataclass
class Settings:
    """User-adjustable analysis thresholds (Settings page)."""

    low_span_threshold: int = 3  # direct reports <= this -> Low Span of Control
    high_span_threshold: int = 12  # direct reports > this -> High Span of Control
    deep_hierarchy_threshold: int = 6  # depth (edges to CEO) > this -> Deep Hierarchy
    small_department_threshold: int = 3  # headcount <= this -> Small Organizational Unit
    high_management_ratio: float = 0.20  # managers / headcount > this -> High Mgmt Ratio
    title_similarity_threshold: float = 0.80  # 0..1, for Similar Job Titles
    exclude_executives_from_span: bool = True  # skip job levels 0-1 in span findings
    max_network_nodes: int = 600  # safety cap for the network chart

    def as_dict(self) -> dict:
        return asdict(self)

    def cache_key(self) -> tuple:
        return tuple(getattr(self, f.name) for f in fields(self))

    @classmethod
    def from_dict(cls, data: dict) -> "Settings":
        known = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in data.items() if k in known})


SETTING_DESCRIPTIONS: dict[str, str] = {
    "low_span_threshold": "Low Span Threshold — مدير لديه عدد موظفين مباشرين أقل من أو يساوي هذا الحد",
    "high_span_threshold": "High Span Threshold — مدير لديه عدد موظفين مباشرين أكبر من هذا الحد",
    "deep_hierarchy_threshold": "Deep Hierarchy Threshold — عمق (عدد العلاقات حتى الـCEO) أكبر من هذا الحد",
    "small_department_threshold": "Small Department Threshold — إدارة عدد موظفيها أقل من أو يساوي هذا الحد",
    "high_management_ratio": "High Management Ratio — نسبة المديرين إلى إجمالي موظفي الإدارة أكبر من هذا الحد",
    "title_similarity_threshold": "Title Similarity — حد التشابه النصي بين المسميات الوظيفية (0-1)",
    "exclude_executives_from_span": "استثناء CEO والـC-Suite من ملاحظات Span of Control",
    "max_network_nodes": "الحد الأقصى لعدد العقد في رسم الشبكة التنظيمية",
}
