"""سجل معاملات مُولَّد مع أنماط احتيال مُعلَّمة، لتدريب أدوات الكشف واختبارها (على غرار PaySim و AMLSim).

الأنماط مأخوذة من التصنيفات العامة المنشورة في أدلة FATF، وكل معاملة احتيالية تحمل تسمية النمط:
- structuring  (التجزئة): إيداعات نقدية متكررة أقل بقليل من حد الإبلاغ.
- round_trip   (التدوير): أموال تدور بين عدة حسابات وتعود لمصدرها بمبالغ متقاربة.
- fake_invoice (فواتير وهمية): شركة صورية تصدر فواتير بمبالغ مستديرة متكررة لمشترٍ واحد.
- mule         (حسابات وسيطة): مبالغ صغيرة من حسابات كثيرة تُجمع ثم تُحوَّل دفعة واحدة.

معامل التمويه (camouflage) يجعل الأنماط أقل وضوحاً: مبالغ أبعد عن الحد، وفترات أطول، ومبالغ غير مستديرة.
الهدف منه إظهار أن القواعد الثابتة تنهار عندما يتكيّف المحتالون، بينما تصمد النماذج أكثر.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

CASH = "CASH"  # إيداع نقدي (لا يوجد حساب مرسل)
TYPOLOGIES = {
    "structuring": "تجزئة الإيداعات",
    "round_trip": "تدوير الأموال",
    "fake_invoice": "فواتير وهمية",
    "mule": "حسابات وسيطة",
}


@dataclass(frozen=True)
class LedgerConfig:
    n_people: int = 600
    n_businesses: int = 150
    days: int = 180
    report_threshold: float = 10_000   # حد الإبلاغ عن الإيداع النقدي
    schemes: int = 15                   # عدد المخططات من كل نمط
    camouflage: float = 0.0             # 0..1: كم يتكيّف المحتالون لتفادي القواعد المعروفة


def _accounts(cfg: LedgerConfig) -> tuple[list[str], list[str]]:
    return [f"P{i:04d}" for i in range(cfg.n_people)], [f"B{i:03d}" for i in range(cfg.n_businesses)]


def _legit(cfg: LedgerConfig, rng: np.random.Generator, people, businesses) -> list[tuple]:
    rows: list[tuple] = []
    employer = rng.choice(businesses, size=len(people))
    salary = np.round(rng.lognormal(np.log(9_000), 0.45, len(people)), 2)
    for day in range(0, cfg.days, 30):  # رواتب شهرية
        rows += [(day, e, p, s, "salary") for p, e, s in zip(people, employer, salary)]
    n = cfg.days * (len(people) + len(businesses)) // 3
    day = rng.integers(0, cfg.days, n)
    # مشتريات أفراد من شركات، ومدفوعات بين الشركات، وتحويلات بين الأفراد، وإيداعات نقدية عادية
    kind = rng.choice(["purchase", "b2b", "p2p", "deposit"], size=n, p=[0.6, 0.15, 0.15, 0.1])
    size = {"purchase": (5.0, 1.1), "b2b": (8.5, 1.2), "p2p": (6.0, 1.0), "deposit": (7.0, 1.0)}
    for k in size:
        m = kind == k
        cnt = int(m.sum())
        amount = np.round(rng.lognormal(*size[k], cnt), 2)
        if k == "purchase":
            src, dst = rng.choice(people, cnt), rng.choice(businesses, cnt)
        elif k == "b2b":
            src, dst = rng.choice(businesses, cnt), rng.choice(businesses, cnt)
        elif k == "p2p":
            src, dst = rng.choice(people, cnt), rng.choice(people, cnt)
        else:
            src, dst = np.full(cnt, CASH), rng.choice(people + businesses, cnt)
        rows += list(zip(day[m], src, dst, amount, np.full(cnt, k)))
    return [(int(d), s, t, float(a), k, "") for d, s, t, a, k in rows if s != t]


def _structuring(cfg, rng, people, businesses, sid) -> list[tuple]:
    acct = rng.choice(people + businesses)
    total = rng.uniform(40_000, 150_000)
    c = cfg.camouflage
    span = int(20 + 100 * c)
    start = rng.integers(0, max(cfg.days - span, 1))
    rows, sent = [], 0.0
    while sent < total:
        amt = round(cfg.report_threshold * rng.uniform(0.85 - 0.45 * c, 0.995), 2)
        rows.append((int(start + rng.integers(0, span)), CASH, acct, amt, "deposit", f"structuring:{sid}"))
        sent += amt
    return rows


def _round_trip(cfg, rng, people, businesses, sid) -> list[tuple]:
    ring = list(rng.choice(businesses, size=int(rng.integers(3, 6)), replace=False))
    amount = rng.uniform(50_000, 400_000)
    day = int(rng.integers(0, cfg.days - 15))
    rows = []
    for i, src in enumerate(ring):
        dst = ring[(i + 1) % len(ring)]
        amount *= rng.uniform(0.97 - 0.3 * cfg.camouflage, 0.995)  # عمولة (أو تغيير متعمد للمبلغ)
        day += int(rng.integers(0, 3 + 12 * cfg.camouflage))
        rows.append((day, src, dst, round(amount, 2), "b2b", f"round_trip:{sid}"))
    return rows


def _fake_invoice(cfg, rng, people, businesses, sid) -> list[tuple]:
    shell, buyer = rng.choice(businesses, size=2, replace=False)
    base = int(rng.choice([5_000, 10_000, 20_000, 25_000]))
    rows = []
    for d in rng.integers(0, cfg.days, int(rng.integers(12, 30))):
        amt = float(base * rng.integers(1, 4))
        if rng.random() < cfg.camouflage:  # مبلغ "طبيعي المظهر" بدل المبلغ المستدير
            amt = round(amt * rng.uniform(0.9, 1.1), 2)
        rows.append((int(d), buyer, shell, amt, "b2b", f"fake_invoice:{sid}"))
    return rows


def _mule(cfg, rng, people, businesses, sid) -> list[tuple]:
    mule, collector = rng.choice(people, size=2, replace=False)
    sources = rng.choice(people, size=int(rng.integers(10, 25)), replace=False)
    span = int(5 + 40 * cfg.camouflage)
    day = int(rng.integers(0, max(cfg.days - span - 5, 1)))
    rows = [(day + int(rng.integers(0, span)), s, mule, round(rng.uniform(500, 3_000), 2), "p2p", f"mule:{sid}")
            for s in sources if s not in (mule, collector)]
    total = sum(r[3] for r in rows) * rng.uniform(0.85, 0.95)
    parts = 1 + int(rng.integers(0, 1 + 4 * cfg.camouflage))  # تقسيم التحويل الأخير على دفعات
    for k in range(parts):
        rows.append((day + span + 1 + k, mule, collector, round(total / parts, 2), "p2p", f"mule:{sid}"))
    return rows


_INJECTORS = {"structuring": _structuring, "round_trip": _round_trip,
              "fake_invoice": _fake_invoice, "mule": _mule}


def simulate_ledger(cfg: LedgerConfig = LedgerConfig(), seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    people, businesses = _accounts(cfg)
    rows = _legit(cfg, rng, people, businesses)
    for typ, inject in _INJECTORS.items():
        for sid in range(cfg.schemes):
            rows += inject(cfg, rng, people, businesses, sid)
    df = pd.DataFrame(rows, columns=["day", "src", "dst", "amount", "kind", "scheme"])
    df["typology"] = df["scheme"].str.split(":").str[0].replace("", None)
    df["is_fraud"] = df["typology"].notna()
    df = df.sort_values(["day", "src"], kind="stable").reset_index(drop=True)
    df.insert(0, "tx_id", np.arange(len(df)))
    return df


def account_labels(ledger: pd.DataFrame) -> pd.DataFrame:
    """تسميات على مستوى الحساب: الحساب مشارك في الاحتيال إذا أرسل أو استقبل معاملة احتيالية."""
    fraud = ledger[ledger.is_fraud]
    # في نمط الحسابات الوسيطة المرسلون غالباً ضحايا، فالمشارك هو المستقبِل فقط (الوسيط والمُجمِّع)
    senders = fraud[fraud.typology != "mule"][["src", "typology"]].rename(columns={"src": "account"})
    receivers = fraud[["dst", "typology"]].rename(columns={"dst": "account"})
    parts = pd.concat([senders, receivers])
    parts = parts[parts.account != CASH]
    accounts = pd.unique(pd.concat([ledger.src, ledger.dst]))
    labels = pd.DataFrame({"account": accounts[accounts != CASH]})
    typ = parts.groupby("account")["typology"].first()
    labels["typology"] = labels.account.map(typ)
    labels["is_fraud"] = labels.typology.notna()
    return labels.set_index("account")
