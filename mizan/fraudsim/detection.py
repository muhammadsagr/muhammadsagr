"""أدوات كشف الاحتيال وتقييمها مقابل التسميات الصحيحة.

- قانون بنفورد: الأرقام الطبيعية يبدأ 30% منها تقريباً بالرقم 1، والمبالغ المختلقة تخالف ذلك.
- التجزئة: عدة إيداعات نقدية بين 85% و100% من حد الإبلاغ.
- الدوائر المغلقة: أموال تعود لمصدرها خلال أيام قليلة بمبالغ متقاربة.
- نموذج انحدار لوجستي (مكتوب بـ numpy) يتعلم من خصائص كل حساب.
"""
from __future__ import annotations

from collections import defaultdict

import numpy as np
import pandas as pd

from .ledger import CASH

BENFORD = np.log10(1 + 1 / np.arange(1, 10))


# ------------------------------------------------------------------ قانون بنفورد
def first_digits(amounts) -> np.ndarray:
    a = np.asarray(amounts, dtype=float)
    a = a[a >= 1]
    return (a / 10 ** np.floor(np.log10(a))).astype(int)


def benford_test(amounts) -> dict:
    """يعيد التوزيع الملاحظ والمتوقع ومتوسط الانحراف المطلق (MAD) وحكم Nigrini."""
    d = first_digits(amounts)
    observed = np.bincount(d, minlength=10)[1:10] / max(len(d), 1)
    mad = float(np.abs(observed - BENFORD).mean())
    verdict = ("مطابقة قريبة" if mad < 0.006 else "مطابقة مقبولة" if mad < 0.012
               else "مطابقة هامشية" if mad < 0.015 else "عدم مطابقة")
    return {"digit": np.arange(1, 10), "observed": observed, "expected": BENFORD,
            "mad": mad, "verdict": verdict, "n": int(len(d))}


# ------------------------------------------------------------------ قواعد
def flag_structuring(ledger: pd.DataFrame, threshold: float, window: int = 30, min_count: int = 3) -> pd.Series:
    """عدد الإيداعات النقدية القريبة من الحد خلال أي نافذة أيام، لكل حساب."""
    near = ledger[(ledger.src == CASH) & ledger.amount.between(0.85 * threshold, threshold, inclusive="left")]
    counts = {}
    for acct, days in near.groupby("dst")["day"]:
        d = np.sort(days.to_numpy())
        best = int(np.max(np.searchsorted(d, d + window) - np.arange(len(d))))
        if best >= min_count:
            counts[acct] = best
    return pd.Series(counts, dtype=int, name="near_threshold_deposits")


def find_cycles(ledger: pd.DataFrame, min_amount: float = 20_000, max_len: int = 5,
                window: int = 15, tolerance: float = 0.1) -> list[dict]:
    """يبحث (DFS) عن مسارات تعود لنقطة البداية بترتيب زمني ومبالغ متقاربة."""
    big = ledger[(ledger.amount >= min_amount) & (ledger.src != CASH)]
    out_edges = defaultdict(list)
    for r in big.itertuples(index=False):
        out_edges[r.src].append((r.dst, r.day, r.amount, r.tx_id))
    found, seen = [], set()

    def dfs(start, node, path, day0, last_day, amt0, txs):
        for dst, day, amt, tx in out_edges.get(node, ()):
            if day < last_day or day - day0 > window or abs(amt / amt0 - 1) > tolerance:
                continue
            if dst == start and len(path) >= 2:
                key = frozenset(txs + [tx])
                if key not in seen:
                    seen.add(key)
                    found.append({"accounts": path[:], "tx_ids": txs + [tx], "amount": amt0, "day": day0})
            elif dst not in path and len(path) < max_len:
                dfs(start, dst, path + [dst], day0, day, amt0, txs + [tx])

    for src, edges in list(out_edges.items()):
        for dst, day, amt, tx in edges:
            if dst != src:
                dfs(src, dst, [src, dst], day, day, amt, [tx])
    return found


# ------------------------------------------------------------------ خصائص الحسابات
def account_features(ledger: pd.DataFrame, threshold: float) -> pd.DataFrame:
    led = ledger[ledger.src != ledger.dst]
    out_ = led[led.src != CASH].groupby("src")
    in_ = led.groupby("dst")
    f = pd.DataFrame({
        "n_out": out_.size(), "sum_out": out_.amount.sum(), "uniq_dst": out_.dst.nunique(),
        "n_in": in_.size(), "sum_in": in_.amount.sum(), "uniq_src": in_.src.nunique(),
    }).fillna(0)
    f = f.drop(index=CASH, errors="ignore")
    f["pass_through"] = np.minimum(f.sum_out, f.sum_in) / np.maximum(f.sum_in, 1)
    both = pd.concat([led[["src", "amount"]].rename(columns={"src": "a"}),
                      led[["dst", "amount"]].rename(columns={"dst": "a"})])
    both = both[both.a != CASH]
    g = both.groupby("a")["amount"]
    f["round_share"] = g.apply(lambda s: np.mean(s % 1000 == 0))
    f["avg_amount_log"] = np.log1p(g.mean())
    cash = led[led.src == CASH]
    f["near_threshold"] = (cash[cash.amount.between(0.85 * threshold, threshold, inclusive="left")]
                           .groupby("dst").size()).reindex(f.index).fillna(0)
    f["fan_in_ratio"] = f.uniq_src / np.maximum(f.uniq_dst, 1)
    # عدد المدفوعات بمبالغ مستديرة كبيرة (المبالغ الحقيقية نادراً ما تكون مضاعفات دقيقة لـ 1000)
    rnd = both[(both.amount >= 5_000) & (both.amount % 1000 == 0)]
    f["round_count"] = rnd.groupby("a").size().reindex(f.index).fillna(0)
    f["burst_senders"] = burst_senders(led).reindex(f.index).fillna(0)
    return f.fillna(0)


def burst_senders(ledger: pd.DataFrame, window: int = 7) -> pd.Series:
    """أكبر عدد من المرسلين المختلفين (تحويلات بين أفراد) خلال أي نافذة أيام، لكل مستقبِل."""
    p2p = ledger[ledger.kind == "p2p"].sort_values("day")
    out = {}
    for acct, g in p2p.groupby("dst"):
        days, srcs = g.day.to_numpy(), g.src.to_numpy()
        ends = np.searchsorted(days, days + window)
        out[acct] = max(len(set(srcs[i:j])) for i, j in enumerate(ends))
    return pd.Series(out, dtype=float)


MODEL_FEATURES = ["pass_through", "round_share", "round_count", "avg_amount_log", "near_threshold",
                  "fan_in_ratio", "burst_senders", "uniq_src", "uniq_dst", "n_in", "n_out"]


class LogisticModel:
    """انحدار لوجستي بسيط بالتدرّج، مع موازنة الأصناف (الاحتيال نادر)."""

    def __init__(self, lr: float = 0.1, epochs: int = 2000, l2: float = 1e-3):
        self.lr, self.epochs, self.l2 = lr, epochs, l2

    def fit(self, X: np.ndarray, y: np.ndarray) -> "LogisticModel":
        X = np.log1p(np.abs(X)) * np.sign(X)
        self.mu, self.sd = X.mean(0), X.std(0) + 1e-9
        Xs = (X - self.mu) / self.sd
        w_pos = len(y) / (2 * max(y.sum(), 1))
        w_neg = len(y) / (2 * max((1 - y).sum(), 1))
        sw = np.where(y == 1, w_pos, w_neg)
        self.w, self.b = np.zeros(X.shape[1]), 0.0
        for _ in range(self.epochs):
            p = 1 / (1 + np.exp(-(Xs @ self.w + self.b)))
            g = sw * (p - y)
            self.w -= self.lr * (Xs.T @ g / len(y) + self.l2 * self.w)
            self.b -= self.lr * g.mean()
        return self

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        X = np.log1p(np.abs(X)) * np.sign(X)
        return 1 / (1 + np.exp(-(((X - self.mu) / self.sd) @ self.w + self.b)))


def collectors(ledger: pd.DataFrame, mules: set, min_amount: float = 5_000) -> set:
    """تتبع الأموال خطوة واحدة: من استقبل تحويلاً كبيراً من حساب وسيط مشتبه به."""
    big = ledger[ledger.src.isin(mules) & (ledger.amount >= min_amount) & (ledger.kind == "p2p")]
    return set(big.dst)


# ------------------------------------------------------------------ التقييم
def evaluate(flagged: set, labels: pd.DataFrame) -> dict:
    truth = set(labels.index[labels.is_fraud])
    tp = len(flagged & truth)
    precision = tp / len(flagged) if flagged else 0.0
    recall = tp / len(truth) if truth else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    by_typ = {t: len(flagged & set(g.index)) / len(g)
              for t, g in labels[labels.is_fraud].groupby("typology")}
    return {"flagged": len(flagged), "tp": tp, "precision": precision, "recall": recall, "f1": f1,
            "recall_by_typology": by_typ}


def run_detectors(ledger: pd.DataFrame, labels: pd.DataFrame, threshold: float,
                  seed: int = 0, test_share: float = 0.5) -> dict:
    """يشغّل كل الكواشف ويقيّمها على نفس مجموعة الاختبار كي تكون المقارنة عادلة."""
    rng = np.random.default_rng(seed)
    feats = account_features(ledger, threshold).reindex(labels.index).fillna(0)
    y = labels.is_fraud.astype(int).to_numpy()
    test = rng.random(len(y)) < test_share
    test_idx = labels.index[test]
    test_labels = labels.loc[test_idx]

    structuring = set(flag_structuring(ledger, threshold).index)
    cycles = find_cycles(ledger)
    in_cycles = {a for c in cycles for a in c["accounts"]}
    # قاعدة الفواتير: مدفوعات متكررة بمبالغ مستديرة كبيرة
    invoices = set(feats.index[feats.round_count >= 8])
    # قاعدة الوسيط: مرسلون كثيرون خلال أيام قليلة، ثم نتتبع أين ذهب المال (المُجمِّع)
    mules = set(feats.index[feats.burst_senders >= 6])
    mules |= collectors(ledger, mules)
    rules = structuring | in_cycles | invoices | mules

    model = LogisticModel().fit(feats[MODEL_FEATURES].to_numpy()[~test], y[~test])
    score = pd.Series(model.predict_proba(feats[MODEL_FEATURES].to_numpy()), index=feats.index)
    ml = set(score.index[score > 0.5])

    tset = set(test_idx)
    results = {
        "تجزئة الإيداعات": evaluate(structuring & tset, test_labels),
        "الدوائر المغلقة": evaluate(in_cycles & tset, test_labels),
        "الفواتير المستديرة": evaluate(invoices & tset, test_labels),
        "الحسابات الوسيطة": evaluate(mules & tset, test_labels),
        "كل القواعد معاً": evaluate(rules & tset, test_labels),
        "نموذج تعلّم آلة": evaluate(ml & tset, test_labels),
        "القواعد + النموذج": evaluate((rules | ml) & tset, test_labels),
    }
    weights = pd.Series(model.w, index=MODEL_FEATURES).sort_values(key=np.abs, ascending=False)
    return {"results": results, "cycles": cycles, "scores": score, "weights": weights,
            "features": feats, "test_accounts": test_idx}
