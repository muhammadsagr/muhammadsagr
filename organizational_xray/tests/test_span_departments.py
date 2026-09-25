import numpy as np

from app import (
    job_title_analysis,
    layer_metrics,
    manager_table,
    Settings,
    span_by,
    span_category,
    span_stats,
    title_similarity,
    unit_metrics,
)
from tests.conftest import make_model


def test_span_category_boundaries():
    s = Settings(low_span_threshold=3, high_span_threshold=12)
    assert span_category(1, s) == "Low"
    assert span_category(3, s) == "Low"
    assert span_category(4, s) == "Within Range"
    assert span_category(12, s) == "Within Range"
    assert span_category(13, s) == "High"


def test_span_stats(small_rows):
    m = make_model(small_rows)
    mt = manager_table(m.df, Settings())
    st = span_stats(mt["direct_reports"])
    # spans: C=2, A=2, B=2, M1=5, M2=1
    assert st["count"] == 5 and st["min"] == 1 and st["max"] == 5
    assert st["median"] == 2 and st["mean"] == 12 / 5
    assert st["p25"] == 2 and st["p75"] == 2
    assert span_stats([])["count"] == 0


def test_span_by_department(small_rows):
    sb = span_by(make_model(small_rows).df, "department", Settings()).set_index("department")
    assert sb.loc["Sales", "managers"] == 3
    assert sb.loc["Sales", "max_span"] == 5


def test_unit_metrics(small_rows):
    u = unit_metrics(make_model(small_rows).df, "department", Settings()).set_index("department")
    assert u.loc["Sales", "headcount"] == 9
    assert u.loc["Sales", "managers"] == 3
    assert abs(u.loc["Sales", "management_ratio"] - 3 / 9) < 1e-9
    assert u.loc["Sales", "layers"] == 3  # depths 1, 2, 3
    assert u.loc["Ops", "headcount"] == 3
    assert u.loc["Sales", "vacancies"] == 0


def test_empty_department_only_vacancies(small_rows):
    rows = small_rows + [("", "C", "Head of ESG", 2, "ESG", None, "Vacant", "PV9")]
    u = unit_metrics(make_model(rows).df, "department", Settings()).set_index("department")
    assert u.loc["ESG", "headcount"] == 0
    assert u.loc["ESG", "vacancies"] == 1
    assert np.isnan(u.loc["ESG", "management_ratio"])


def test_layer_metrics(small_rows):
    lm = layer_metrics(make_model(small_rows).df, "job_level").set_index("layer")
    assert lm.loc[6, "employees"] == 8
    assert lm.loc[0, "layer_name"] == "CEO"
    assert abs(lm["pct_of_total"].sum() - 1) < 1e-9
    ld = layer_metrics(make_model(small_rows).df, "depth")
    assert ld["employees"].sum() == 13


def test_title_similarity_rules():
    assert title_similarity("HR Analyst", "hr  analyst") == 1.0
    assert title_similarity("L&D Specialist", "Learning & Development Specialist") == 0.95
    assert title_similarity("HR Analyst", "HRIS Analyst") > 0.85
    assert title_similarity("HR Analyst", "HR Data Analyst") >= 0.8
    assert title_similarity("Brand Specialist", "HR Specialist") == 0.0


def test_job_title_analysis_dummy(dummy_model):
    jt = job_title_analysis(dummy_model.df, Settings())
    variants = " ".join(jt["variants"]["variants"])
    assert "HRIS Analyst" in variants and "Hris Analyst" in variants
    assert "hr analyst" in variants
    pairs = {frozenset((a, b)) for a, b in zip(jt["similar"]["title_a"], jt["similar"]["title_b"])}
    assert frozenset(("L&D Specialist", "Learning & Development Specialist")) in pairs
    # career ladders are not reported as duplicates
    assert frozenset(("Accountant", "Senior Accountant")) not in pairs
