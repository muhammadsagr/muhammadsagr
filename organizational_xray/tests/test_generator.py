from data.dummy_generator import generate_org
from utils.config import CANONICAL_COLUMNS


def test_generator_shape_and_fields(dummy, dummy_model):
    df, manifest = dummy
    assert list(df.columns) == CANONICAL_COLUMNS
    active = dummy_model.df["is_active"].sum()
    assert 1350 <= active <= 1650
    assert (df["position_status"] == "Vacant").sum() > 20
    assert df["department"].nunique() >= 20
    assert len(manifest) >= 15


def test_generator_is_deterministic():
    a, _ = generate_org(1500, 7)
    b, _ = generate_org(1500, 7)
    assert a.equals(b)


def test_departments_differ(dummy_model):
    d = dummy_model.df[dummy_model.df["is_active"]]
    g = d.groupby("department")["depth"].max()
    assert g["Operations"] - g["Business Development"] >= 4  # deep vs flat


def test_scaling():
    df, _ = generate_org(5000, 1)
    assert 4000 <= (df["employment_status"].isin(["Active", "On Leave"])).sum() <= 6000
