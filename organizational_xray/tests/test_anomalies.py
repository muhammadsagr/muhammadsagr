from app import (
    detect_findings,
    explain_finding,
    filter_findings,
    FINDING_TYPES,
    Settings,
    SEVERITIES,
)
from tests.conftest import make_model

FORBIDDEN = ["غير ضروري", "unnecessary", "Bad", "Good"]


def types(f):
    return set(f["type"])


def test_small_org_findings(small_rows):
    m = make_model(small_rows)
    f = detect_findings(m, Settings())
    # M2 has 1 report, A and B have 2 -> low span (CEO excluded as executive)
    low = f[f["type"].eq("LOW_SPAN_OF_CONTROL")]
    assert set(low["entity_id"]) == {"M2", "A", "B"}
    assert "HIGH_SPAN_OF_CONTROL" not in types(f)
    assert set(f["severity"]) <= set(SEVERITIES)
    assert f["finding_id"].is_unique


def test_high_span_and_explainability(small_rows):
    rows = small_rows + [(f"x{i}", "M2", "Sales Rep", 6, "Sales") for i in range(20)]
    m = make_model(rows)
    f = detect_findings(m, Settings(high_span_threshold=12))
    hi = f[f["type"].eq("HIGH_SPAN_OF_CONTROL")]
    assert list(hi["entity_id"]) == ["M2"]
    r = hi.iloc[0]
    assert r["value"] == 21 and r["threshold"] == 12
    assert "21" in r["evidence"] and "Organizational median" in r["benchmark"]
    e = explain_finding(f, r["finding_id"], m)
    assert len(e["records"]) == 22  # the manager + 21 reports
    assert "direct_reports > High Span Threshold" in e["rule"]


def test_low_span_wording_is_neutral(small_rows):
    f = detect_findings(make_model(small_rows), Settings())
    text = " ".join(f["description"]) + " ".join(f["evidence"])
    assert "يحتاج إلى مراجعة" in text
    for word in FORBIDDEN:
        assert word not in " ".join(f["description"])


def test_reporting_findings(small_rows):
    rows = [r if r[0] != "M1" else ("M1", "A", "Sales Manager", 4, "Sales", "Terminated")
            for r in small_rows]
    rows += [("o", "", "X", 6, "Ops"), ("i", "GHOST", "X", 6, "Ops"),
             ("p", "q", "X", 6, "Ops"), ("q", "p", "X", 6, "Ops")]
    f = detect_findings(make_model(rows), Settings())
    assert {"ORPHAN_EMPLOYEE", "INVALID_MANAGER", "TERMINATED_MANAGER", "CIRCULAR_REPORTING"} <= types(f)
    term = f[f["type"].eq("TERMINATED_MANAGER")].iloc[0]
    assert term["entity_id"] == "M1" and term["value"] == 5
    assert f[f["type"].eq("CIRCULAR_REPORTING")].iloc[0]["severity"] == "Critical"


def test_unit_findings(small_rows):
    rows = small_rows + [("t", "C", "Treasurer", 2, "Treasury")]
    f = detect_findings(make_model(rows), Settings(small_department_threshold=3,
                                                   high_management_ratio=0.2))
    small = set(f.loc[f["type"].eq("SMALL_DEPARTMENT"), "department"])
    assert {"Treasury", "Exec", "Ops"} <= small
    hm = f[f["type"].eq("HIGH_MANAGEMENT_RATIO")]
    assert list(hm["department"]) == ["Sales"]  # 3 / 9 = 33%


def test_deep_hierarchy_threshold(small_rows):
    f = detect_findings(make_model(small_rows), Settings(deep_hierarchy_threshold=2))
    deep = f[f["type"].eq("DEEP_HIERARCHY")]
    assert list(deep["department"]) == ["Sales"]
    assert deep.iloc[0]["value"] == 3
    assert "DEEP_HIERARCHY" not in types(detect_findings(make_model(small_rows), Settings()))


def test_vacancy_and_duplicates(small_rows):
    rows = small_rows + [("", "M2", "Sales Rep", 6, "Sales", None, "Vacant", "PV1"),
                         ("d1", "M2", "Sales Rep", 6, "Sales", None, None, "P0001")]
    f = detect_findings(make_model(rows), Settings())
    assert "VACANT_POSITION" in types(f)
    dup = f[f["type"].eq("DUPLICATE_POSITION") & f["entity_id"].eq("P0001")]
    assert len(dup) == 1 and set(dup.iloc[0]["related_ids"]) == {"C", "d1"}


def test_filter_findings(small_rows):
    m = make_model(small_rows)
    f = detect_findings(m, Settings())
    ops = filter_findings(f, {"B", "e7", "e8"}, {"Ops"})
    assert set(ops["entity_id"]) <= {"B", "Ops"}


def test_dummy_detects_every_injected_issue(dummy, dummy_model):
    df, manifest = dummy
    f = detect_findings(dummy_model, Settings())
    assert set(FINDING_TYPES) <= types(f)
    related = set().union(*f["related_ids"].map(set))
    for m in manifest:
        if m["expected_finding"] in FINDING_TYPES:
            assert set(m["ids"]) <= related, m
    hi = f[f["type"].eq("HIGH_SPAN_OF_CONTROL")]["value"]
    assert hi.max() >= 30 and (hi >= 15).sum() >= 3
    low = f[f["type"].eq("LOW_SPAN_OF_CONTROL")]["value"]
    assert {1, 2, 3} <= set(low)
    deep = f[f["type"].eq("DEEP_HIERARCHY")]
    assert "Operations" in set(deep["department"])
    assert "HRIS" in set(f.loc[f["type"].eq("HIGH_MANAGEMENT_RATIO"), "department"])
