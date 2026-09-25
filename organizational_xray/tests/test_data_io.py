import io

import pandas as pd

from app import (
    affected_records,
    build_export_tables,
    call_tool,
    dimension_scores,
    normalize,
    OrgXRayEngine,
    read_uploaded,
    run_checks,
    Settings,
    to_csv_bytes,
    to_excel_bytes,
    TOOL_SPECS,
    validate,
)
from tests.conftest import make_model, make_raw


def test_column_aliases_and_normalisation():
    raw = pd.DataFrame({"Employee ID": ["1", "2.0"], "Name": ["a", "b"], "Reports To": ["", "1"],
                        "job title": ["CEO", "X"], "Level": ["L0", "6"], "Status": ["active", "LOA"],
                        "Salary": ["1,000", "abc"]})
    df = normalize(raw)
    assert list(df["employee_id"]) == ["1", "2"]
    assert list(df["manager_id"]) == ["", "1"]
    assert list(df["job_level"]) == [0, 6]
    assert list(df["employment_status"]) == ["Active", "On Leave"]
    assert df.loc[0, "salary"] == 1000 and pd.isna(df.loc[1, "salary"])
    assert df["is_active"].all()


def test_validator_errors_and_warnings():
    assert not validate(pd.DataFrame()).ok
    rep = validate(pd.DataFrame({"Name": ["a"]}))
    assert not rep.ok and "employee_id" in rep.missing_columns
    raw = make_raw([("C", "", "CEO", 0, "E"), ("a", "C", "X", 6, "E"), ("a", "ZZ", "X", 6, "E")])
    rep = validate(raw)
    assert rep.ok
    msgs = " ".join(rep.to_frame()["Message"])
    assert "مكرر" in msgs and "غير موجود" in msgs


def test_read_csv_and_excel_roundtrip(small_rows):
    raw = make_raw(small_rows)
    csv = read_uploaded(to_csv_bytes(raw), "x.csv")
    xlsx = read_uploaded(to_excel_bytes({"Employees": raw}), "x.xlsx")
    for df in (csv, xlsx):
        m = make_model_from(df)
        assert m.ceo_id == "C"


def make_model_from(raw):
    from app import build_org_model
    return build_org_model(normalize(raw))


def test_data_quality_checks(small_rows):
    rows = small_rows + [("e1", "M2", "Sales Rep", 6, "Sales"), ("x", "GHOST", "", 6, "")]
    m = make_model(rows)
    checks = run_checks(m).set_index("check_id")
    assert checks.loc["U01", "failed"] == 2
    assert checks.loc["C04", "failed"] == 1 and checks.loc["C05", "failed"] == 1
    assert checks.loc["R01", "failed"] == 1
    assert checks.loc["C01", "score"] == 1.0
    recs = affected_records(m, checks.reset_index(), "R01")
    assert list(recs["node_id"]) == ["x"]
    assert set(dimension_scores(checks.reset_index())["dimension"]) == {
        "Completeness", "Uniqueness", "Validity", "Consistency", "Referential Integrity"}


def test_dummy_data_quality(dummy_model):
    checks = run_checks(dummy_model).set_index("check_id")
    assert checks.loc["C03", "failed"] == 3  # orphan employees
    assert checks.loc["U02", "failed"] == 4  # two duplicated position IDs
    assert checks.loc["S01", "failed"] == 2  # terminated managers still "Filled"


def test_export_workbook(small_rows):
    from app import detect_findings
    m = make_model(small_rows)
    sheets = build_export_tables(m, detect_findings(m), Settings())
    assert list(sheets) == ["Employees", "Managers", "Departments", "Findings", "Span of Control",
                            "Organizational Layers", "Data Quality"]
    xls = pd.ExcelFile(io.BytesIO(to_excel_bytes(sheets)))
    assert xls.sheet_names == list(sheets)
    assert len(pd.read_excel(xls, "Employees")) == 13


def test_engine_tools(dummy):
    e = OrgXRayEngine(dummy[0])
    s = call_tool(e, "summary")
    assert s["Employees"] > 1400
    top = call_tool(e, "departments_by", {"metric": "management_ratio", "top": 1})
    assert top[0]["department"] == "HRIS"
    low = call_tool(e, "managers_by_span", {"max_reports": 2})
    assert all(r["direct_reports"] <= 2 for r in low)
    chains = call_tool(e, "longest_reporting_chains", {"top": 3})
    assert chains[0]["depth"] == 8
    fid = call_tool(e, "list_findings", {"finding_type": "DEEP_HIERARCHY"})[0]["finding_id"]
    assert call_tool(e, "explain", {"finding_id": fid})["rule"]
    assert call_tool(e, "explain_department", {"department": "Operations"})["findings"]
    assert {t["name"] for t in TOOL_SPECS} <= set(dir(e))
