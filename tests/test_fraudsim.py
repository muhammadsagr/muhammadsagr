import numpy as np
import pandas as pd
import pytest

from mizan.fraudsim.detection import benford_test, find_cycles, flag_structuring, run_detectors
from mizan.fraudsim.ledger import CASH, LedgerConfig, account_labels, simulate_ledger
from mizan.fraudsim.tax import TaxPolicy, generate_population, optimal_declaration, simulate


# ------------------------------------------------------------------ التهرب الضريبي
def test_declaration_responds_to_deterrence():
    rho, cap = np.full(3, 2.0), np.full(3, 0.5)
    low = optimal_declaration(np.full(3, 0.01), rho, cap, 0.2, 1.0, moral=0.2)
    high = optimal_declaration(np.full(3, 0.30), rho, cap, 0.2, 1.0, moral=0.2)
    assert (high >= low).all() and high[0] > low[0]
    # إذا كانت المقامرة خاسرة في المتوسط (p·(1+f) ≥ 1) لا أحد يتهرب
    assert optimal_declaration([0.5], [1.0], [0.5], 0.2, 1.5) == pytest.approx([1.0])
    # من لا يملك فرصة الإخفاء يصرّح بكل شيء
    assert optimal_declaration([0.001], [1.0], [0.0], 0.3, 0.0) == pytest.approx([1.0])


def test_more_audits_shrink_the_tax_gap():
    pop = generate_population(2000, seed=1)
    gap = {}
    for rate in (0.01, 0.10):
        yearly, _ = simulate(pop, TaxPolicy(audit_rate=rate), years=6, seed=1)
        gap[rate] = yearly.tax_gap.iloc[-1] / yearly.tax_due.iloc[-1]
    assert gap[0.10] < gap[0.01]


def test_targeting_improves_hit_rate():
    pop = generate_population(2000, seed=2)
    hits = {t: simulate(pop, TaxPolicy(targeting=t, signal_noise=0.2), years=3, seed=2)[0].hit_rate.mean()
            for t in (0.0, 1.0)}
    assert hits[1.0] > hits[0.0] + 0.1


def test_honest_and_salaried_hide_nothing_meaningful():
    pop = generate_population(2000, seed=3)
    _, people = simulate(pop, TaxPolicy(audit_rate=0.005, penalty=0.0), years=2, seed=3)
    assert (people.loc[people.honest, "declared_share"] == 1).all()
    assert people.loc[people.sector == "موظفون برواتب", "declared_share"].min() >= 0.95


# ------------------------------------------------------------------ السجل والكشف
@pytest.fixture(scope="module")
def world():
    cfg = LedgerConfig(n_people=300, n_businesses=80, days=120, schemes=8)
    ledger = simulate_ledger(cfg, seed=4)
    return cfg, ledger, account_labels(ledger)


def test_ledger_is_labelled_and_deterministic(world):
    cfg, ledger, labels = world
    assert set(ledger.typology.dropna()) == {"structuring", "round_trip", "fake_invoice", "mule"}
    assert ledger.is_fraud.sum() > 0 and labels.is_fraud.sum() > 0
    assert CASH not in labels.index
    pd.testing.assert_frame_equal(ledger, simulate_ledger(cfg, seed=4))


def test_benford_separates_natural_from_invented_amounts(world):
    _, ledger, _ = world
    assert benford_test(ledger.loc[~ledger.is_fraud, "amount"])["mad"] < 0.012
    assert benford_test(ledger.loc[ledger.typology == "fake_invoice", "amount"])["mad"] > 0.015


def test_structuring_and_cycle_rules_find_injected_schemes(world):
    cfg, ledger, labels = world
    flagged = set(flag_structuring(ledger, cfg.report_threshold).index)
    truth = set(labels.index[labels.typology == "structuring"])
    assert truth and truth <= flagged
    cycle_txs = {t for c in find_cycles(ledger) for t in c["tx_ids"]}
    assert set(ledger.loc[ledger.typology == "round_trip", "tx_id"]) <= cycle_txs


def test_find_cycles_respects_time_order():
    ledger = pd.DataFrame({"tx_id": [0, 1, 2], "day": [5, 1, 6], "src": ["A", "B", "C"],
                           "dst": ["B", "C", "A"], "amount": [50_000, 49_000, 48_000]})
    assert find_cycles(ledger) == []  # لا يوجد ترتيب زمني يجعل المال يدور ويعود
    ledger["day"] = [5, 6, 7]
    assert [c["accounts"] for c in find_cycles(ledger)] == [["A", "B", "C"]]


def test_camouflage_hurts_rules_more_than_the_model():
    recall = {}
    for c in (0.0, 1.0):
        cfg = LedgerConfig(camouflage=c)
        ledger = simulate_ledger(cfg, seed=0)
        res = run_detectors(ledger, account_labels(ledger), cfg.report_threshold, seed=0)["results"]
        recall[c] = (res["كل القواعد معاً"]["recall"], res["نموذج تعلّم آلة"]["recall"])
    assert recall[0.0][0] > 0.9
    assert recall[1.0][0] < 0.5 < recall[1.0][1]
