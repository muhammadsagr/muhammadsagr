import numpy as np
import pandas as pd
import pytest

from mizan import analytics
from mizan.collector import collect
from mizan.sources import CSVSource, SyntheticSource
from mizan.store import MAGIC, RECORD_SIZE, CorruptFileError, TimeSeriesStore


def make_df(dates, base=1.0):
    idx = pd.DatetimeIndex(pd.to_datetime(dates), name="date")
    n = len(idx)
    v = base + np.arange(n, dtype=float)
    return pd.DataFrame({"open": v, "high": v + 1, "low": v - 1, "close": v, "volume": v * 10}, index=idx)


# ------------------------------------------------------------------ المخزن
def test_store_roundtrip_and_range(tmp_path):
    store = TimeSeriesStore(tmp_path)
    df = make_df(["2024-01-02", "2024-01-03", "2024-01-04"])
    assert store.write("ABC", df) == 3
    pd.testing.assert_frame_equal(store.read("ABC"), df, check_freq=False)
    part = store.read("ABC", "2024-01-03", "2024-01-03")
    assert list(part.index) == [pd.Timestamp("2024-01-03")]
    assert store.date_range("ABC") == (pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-04"))
    assert store.symbols() == ["ABC"]


def test_store_last_write_wins_and_compact(tmp_path):
    store = TimeSeriesStore(tmp_path)
    store.write("ABC", make_df(["2024-01-03", "2024-01-02"]))
    store.write("ABC", make_df(["2024-01-03"], base=99))
    out = store.read("ABC")
    assert list(out.index) == list(pd.to_datetime(["2024-01-02", "2024-01-03"]))
    assert out.loc["2024-01-03", "close"] == 99
    store.compact("ABC")
    assert (tmp_path / "ABC.mzn").stat().st_size == len(MAGIC) + 2 * RECORD_SIZE
    pd.testing.assert_frame_equal(TimeSeriesStore(tmp_path).read("ABC"), out)


def test_store_recovers_from_torn_write(tmp_path):
    store = TimeSeriesStore(tmp_path)
    store.write("ABC", make_df(["2024-01-02", "2024-01-03"]))
    path = tmp_path / "ABC.mzn"
    with open(path, "ab") as f:
        f.write(b"\x01" * (RECORD_SIZE - 5))  # سجل مقطوع كأن التيار انقطع
    fresh = TimeSeriesStore(tmp_path)
    assert len(fresh.read("ABC")) == 2
    assert path.stat().st_size == len(MAGIC) + 2 * RECORD_SIZE


def test_store_detects_corrupted_record(tmp_path):
    store = TimeSeriesStore(tmp_path)
    store.write("ABC", make_df(["2024-01-02", "2024-01-03"]))
    path = tmp_path / "ABC.mzn"
    data = bytearray(path.read_bytes())
    data[len(MAGIC) + RECORD_SIZE + 10] ^= 0xFF  # إفساد السجل الثاني
    path.write_bytes(bytes(data))
    assert len(TimeSeriesStore(tmp_path).read("ABC")) == 1


def test_store_rejects_bad_input(tmp_path):
    store = TimeSeriesStore(tmp_path)
    with pytest.raises(ValueError):
        store.read("../etc/passwd")
    (tmp_path / "BAD.mzn").write_bytes(b"nope")
    with pytest.raises(CorruptFileError):
        store.read("BAD")


# ------------------------------------------------------------------ المصادر والجامع
def test_synthetic_is_deterministic_and_consistent():
    src = SyntheticSource(seed=1)
    a = src.fetch("BANK", "2023-01-01", "2023-06-30")
    b = src.fetch("BANK", "2023-03-01", "2023-12-31")
    common = a.index.intersection(b.index)
    assert len(common) > 50
    pd.testing.assert_frame_equal(a.loc[common], b.loc[common])  # نفس اليوم = نفس السعر مهما كان النطاق
    assert (a["high"] >= a[["open", "close"]].max(axis=1)).all()
    assert (a["low"] <= a[["open", "close"]].min(axis=1)).all()


def test_synthetic_assets_are_correlated():
    src = SyntheticSource()
    r = pd.DataFrame({s: src.fetch(s, "2020-01-01", "2024-12-31")["close"] for s in ["BANK", "PETCHEM"]}).pct_change()
    assert r.corr().iloc[0, 1] > 0.3


def test_csv_source_uses_adjusted_close(tmp_path):
    (tmp_path / "XYZ.csv").write_text(
        "Date,Open,High,Low,Close,Adj Close,Volume\n"
        "2024-01-03,10,11,9,10,5,100\n2024-01-02,8,9,7,8,4,100\n"
    )
    df = CSVSource(tmp_path).fetch("XYZ", "2024-01-01", "2024-12-31")
    assert list(df.index) == list(pd.to_datetime(["2024-01-02", "2024-01-03"]))
    assert df["close"].tolist() == [4, 5] and df.loc["2024-01-03", "high"] == 5.5


def test_collect_is_incremental_and_isolates_errors(tmp_path):
    store = TimeSeriesStore(tmp_path)
    src = SyntheticSource()
    first = collect(src, ["BANK", "NOPE"], "2024-01-01", "2024-03-31", store)
    assert first[0].rows > 0 and first[0].error is None
    assert first[1].error is not None
    again = collect(src, ["BANK"], "2024-01-01", "2024-03-31", store)
    assert again[0].rows == 0
    more = collect(src, ["BANK"], "2024-01-01", "2024-04-30", store)
    assert 0 < more[0].rows < first[0].rows
    assert store.date_range("BANK")[1] == pd.Timestamp("2024-04-30")


# ------------------------------------------------------------------ التحليلات
def test_analytics_basics():
    idx = pd.bdate_range("2024-01-01", periods=4)
    prices = pd.DataFrame({"A": [100, 110, 99, 120], "B": [50, 50, 50, 50]}, index=idx, dtype=float)
    assert analytics.rebase(prices).iloc[0].tolist() == [100, 100]
    assert analytics.max_drawdown(prices["A"]) == pytest.approx(99 / 110 - 1)
    assert analytics.simple_returns(prices)["A"].tolist() == pytest.approx([0.1, -0.1, 120 / 99 - 1])
    s = analytics.summary(prices)
    assert s.loc["A", "total_return"] == pytest.approx(0.2)
    assert s.loc["B", "volatility"] == 0 and s.loc["B", "max_drawdown"] == 0
