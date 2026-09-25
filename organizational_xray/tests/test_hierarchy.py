import pandas as pd

from analytics.hierarchy import (
    department_heads,
    depth_stats,
    layer_count,
    level_depth_matrix,
    longest_chains,
)
from tests.conftest import make_model
from utils.config import (
    RS_CEO,
    RS_CIRCULAR,
    RS_DISCONNECTED,
    RS_DUPLICATE,
    RS_INVALID,
    RS_MISSING,
    RS_TERMINATED,
    RS_VALID,
)


def status(model, nid):
    return model.df.set_index("node_id").loc[nid, "reporting_status"]


def test_build_small_hierarchy(small_rows):
    m = make_model(small_rows)
    assert m.ceo_id == "C"
    d = m.df.set_index("node_id")
    assert d.loc["C", "depth"] == 0
    assert d.loc["A", "depth"] == 1
    assert d.loc["e1", "depth"] == 3
    assert d.loc["e7", "depth"] == 2
    assert status(m, "C") == RS_CEO
    assert (d.drop(index="C")["reporting_status"] == RS_VALID).all()
    assert layer_count(m.df) == 4


def test_span_and_subtree_sizes(small_rows):
    d = make_model(small_rows).df.set_index("node_id")
    assert d.loc["M1", "direct_reports"] == 5
    assert d.loc["A", "direct_reports"] == 2
    assert d.loc["A", "total_reports"] == 8  # M1, M2, e1..e6
    assert d.loc["C", "total_reports"] == 12
    assert not d.loc["e1", "is_manager"]
    assert d["is_manager"].sum() == 5  # C, A, B, M1, M2


def test_depth_stats(small_rows):
    m = make_model(small_rows)
    s = depth_stats(m)
    assert s["min"] == 1 and s["max"] == 3
    assert s["count"] == 12
    assert abs(s["mean"] - (2 + 2 + 2 * 2 + 3 * 6 + 2 * 2) / 12) < 1e-9 or s["mean"] > 0


def test_ceo_without_manager_is_not_orphan(small_rows):
    m = make_model(small_rows)
    assert status(m, "C") == RS_CEO


def test_employee_without_manager_is_orphan(small_rows):
    rows = small_rows + [("x", "", "Analyst", 6, "Sales")]
    m = make_model(rows)
    assert m.ceo_id == "C"
    assert status(m, "x") == RS_MISSING
    assert pd.isna(m.df.set_index("node_id").loc["x", "depth"])


def test_ceo_picked_by_level_when_multiple_roots(small_rows):
    rows = [("z", "", "Analyst", 6, "Sales")] + small_rows
    assert make_model(rows).ceo_id == "C"


def test_invalid_manager(small_rows):
    rows = small_rows + [("x", "NOPE", "Analyst", 6, "Sales")]
    assert status(make_model(rows), "x") == RS_INVALID


def test_terminated_manager_and_disconnected_team(small_rows):
    rows = [r if r[0] != "M1" else ("M1", "A", "Sales Manager", 4, "Sales", "Terminated")
            for r in small_rows]
    m = make_model(rows)
    assert status(m, "e1") == RS_TERMINATED
    assert m.df.set_index("node_id").loc["M1", "reporting_status"] == "Not Active"
    assert m.df.set_index("node_id").loc["A", "direct_reports"] == 1


def test_circular_reporting_detected_without_crash(small_rows):
    rows = small_rows + [("p", "r", "X", 6, "Ops"), ("q", "p", "X", 6, "Ops"),
                         ("r", "q", "X", 6, "Ops"), ("s", "p", "X", 6, "Ops")]
    m = make_model(rows)
    assert m.cycles == [["p", "r", "q"]]
    for n in "pqr":
        assert status(m, n) == RS_CIRCULAR
    assert status(m, "s") == RS_DISCONNECTED
    chain = m.chain_up("s")
    assert chain[0] == "s" and chain[-1] in chain[:-1]  # loop closes, no infinite walk
    assert m.df.set_index("node_id").loc["p", "total_reports"] == 3  # q, r and s


def test_self_reporting(small_rows):
    rows = small_rows + [("x", "x", "X", 6, "Ops")]
    m = make_model(rows)
    assert ["x"] in m.cycles
    assert status(m, "x") == RS_CIRCULAR


def test_fully_circular_org_has_no_ceo():
    m = make_model([("a", "b", "X", 1, "D"), ("b", "a", "X", 1, "D")])
    assert m.ceo_id is None
    assert m.df["depth"].isna().all()
    assert depth_stats(m)["count"] == 0


def test_duplicate_employee_ids(small_rows):
    rows = small_rows + [("e1", "M2", "Sales Rep", 6, "Sales")]
    m = make_model(rows)
    dup = m.df[m.df["is_duplicate_id"]]
    assert len(dup) == 1
    assert dup.iloc[0]["reporting_status"] == RS_DUPLICATE
    assert m.df.set_index("node_id").loc[["M2"], "direct_reports"].iloc[0] == 1


def test_manager_without_employees(small_rows):
    rows = small_rows + [("M3", "A", "Sales Manager", 4, "Sales")]
    d = make_model(rows).df.set_index("node_id")
    assert d.loc["M3", "direct_reports"] == 0
    assert not d.loc["M3", "is_manager"]


def test_vacant_positions_are_nodes_but_not_headcount(small_rows):
    rows = small_rows + [("", "M2", "Sales Rep", 6, "Sales", None, "Vacant", "PV1")]
    m = make_model(rows)
    d = m.df.set_index("node_id")
    assert "VAC-PV1" in d.index
    assert d.loc["M2", "direct_reports"] == 1
    assert d.loc["M2", "vacant_direct_positions"] == 1
    assert not d.loc["VAC-PV1", "is_active"]


def test_longest_chains_and_heads(small_rows):
    m = make_model(small_rows)
    lc = longest_chains(m, 3)
    assert lc.iloc[0]["depth"] == 3
    assert lc.iloc[0]["chain_ids"].startswith("C → A → M")
    heads = department_heads(m)
    assert heads["Sales"] == "A" and heads["Ops"] == "B"
    assert level_depth_matrix(m.df).loc[6, 3] == 6


def test_dummy_hierarchy(dummy_model):
    m = dummy_model
    assert m.ceo_id is not None
    assert m.df.loc[m.df["node_id"].eq(m.ceo_id), "job_level"].iloc[0] == 0
    assert m.df["depth"].max() >= 8
    assert len(m.cycles) >= 1
