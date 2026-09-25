import pytest

from app import apply_scenario, compare, normalize, Settings, SimulationError
from tests.conftest import make_model, make_raw


def run(rows, actions):
    df = normalize(make_raw(rows))
    before = make_model(rows)
    snapshot = df.copy()
    res = apply_scenario(df, actions, before)
    assert df.equals(snapshot)  # source data is never modified
    return before, res, compare(before, res.model, Settings())


def span(model, nid):
    d = model.df.set_index("node_id")
    return int(d.loc[nid, "direct_reports"])


def test_merge_departments(small_rows):
    before, res, cmp = run(small_rows, [{"type": "merge_departments",
                                         "departments": ["Sales", "Ops"], "new_name": "Commercial"}])
    assert set(res.model.df["department"]) == {"Exec", "Commercial"}
    dc = cmp["department_changes"].set_index("department")
    assert dc.loc["Commercial", "headcount_after"] == 12


def test_merge_with_consolidated_leadership(small_rows):
    before, res, cmp = run(small_rows, [{"type": "merge_departments", "departments": ["Sales", "Ops"],
                                         "new_name": "Commercial", "consolidate_heads": True}])
    assert "B" not in set(res.model.df["node_id"])
    assert span(res.model, "A") == 4  # M1, M2, e7, e8
    assert cmp["after"]["Employees"] == 12


def test_remove_layer(small_rows):
    before, res, cmp = run(small_rows, [{"type": "remove_layer", "job_level": 4}])
    ids = set(res.model.df["node_id"])
    assert not {"M1", "M2"} & ids
    assert span(res.model, "A") == 6
    assert cmp["before"]["Layers"] == 4 and cmp["after"]["Layers"] == 3
    assert any("Direct Reports 2 → 6" in line for line in cmp["narrative"])


def test_move_employee(small_rows):
    before, res, cmp = run(small_rows, [{"type": "move_employee", "employee_id": "e1",
                                         "new_manager_id": "B", "move_department": True}])
    assert span(res.model, "M1") == 4 and span(res.model, "B") == 3
    d = res.model.df.set_index("node_id")
    assert d.loc["e1", "depth"] == 2 and d.loc["e1", "department"] == "Ops"


def test_move_employee_rejects_cycles(small_rows):
    with pytest.raises(SimulationError):
        run(small_rows, [{"type": "move_employee", "employee_id": "A", "new_manager_id": "e1"}])
    with pytest.raises(SimulationError):
        run(small_rows, [{"type": "move_employee", "employee_id": "A", "new_manager_id": "A"}])


@pytest.mark.parametrize("target,expected", [("manager_of_removed", "A"),
                                             ("department_head", "A"), ("B", "B")])
def test_remove_manager(small_rows, target, expected):
    before, res, cmp = run(small_rows, [{"type": "remove_manager", "manager_id": "M1",
                                         "reassign_to": target}])
    assert "M1" not in set(res.model.df["node_id"])
    d = res.model.df.set_index("node_id")
    assert (d.loc[["e1", "e2", "e3", "e4", "e5"], "manager_id"] == expected).all()
    assert cmp["after"]["Managers"] == cmp["before"]["Managers"] - 1


def test_remove_manager_promote_direct_report(small_rows):
    before, res, _ = run(small_rows, [{"type": "remove_manager", "manager_id": "M1",
                                       "reassign_to": "e1"}])
    d = res.model.df.set_index("node_id")
    assert d.loc["e1", "manager_id"] == "A"
    assert span(res.model, "e1") == 4


def test_remove_ceo_rejected(small_rows):
    with pytest.raises(SimulationError):
        run(small_rows, [{"type": "remove_manager", "manager_id": "C"}])


def test_scenario_chain_and_unknown_action(small_rows):
    _, res, cmp = run(small_rows, [{"type": "remove_layer", "job_level": 4},
                                   {"type": "move_employee", "employee_id": "e7",
                                    "new_manager_id": "A"}])
    assert len(res.log) == 2
    with pytest.raises(SimulationError):
        run(small_rows, [{"type": "explode"}])


def test_simulation_on_dummy(dummy):
    from app import OrgXRayEngine
    e = OrgXRayEngine(dummy[0])
    out = e.simulate([{"type": "merge_departments", "departments": ["HRIS", "HR Operations"],
                       "new_name": "HR Operations & HRIS", "consolidate_heads": True}])
    metrics = {r["Metric"]: r for r in out["summary"]}
    assert metrics["Departments"]["After (fmt)"] != metrics["Departments"]["Before (fmt)"]
