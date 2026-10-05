"""نموذج التهرب الضريبي القائم على الوكلاء.

كل دافع ضرائب يختار نسبة الدخل التي يصرّح بها لتعظيم المنفعة المتوقعة (نموذج Allingham–Sandmo 1972):
    إن لم يُدقَّق عليه:  W1 = I - t·D
    إن دُقِّق وكُشف:     W2 = I - t·I - f·t·(I - D)   (يدفع الضريبة كاملة + الغرامة، صيغة Yitzhaki)
    EU = (1 - p)·u(W1) + p·u(W2)      حيث u منفعة CRRA و p احتمال التدقيق كما *يتصوره* هو.

إضافات تقرّب النموذج من الواقع:
- **الفرصة:** الموظف الذي يُبلغ صاحب العمل عن راتبه لا يستطيع إخفاء إلا القليل، بعكس النشاط النقدي.
- **الكلفة الأخلاقية:** النموذج الأصلي يتنبأ بتهرب أكبر بكثير من الواقع. لذلك نضيف كلفة نفسية/اجتماعية
  تتزايد مع حجم الإخفاء: m·h² (h = نسبة الدخل المخفية)، وتختلف m من شخص لآخر.
- **الأمانة الذاتية:** نسبة من الناس تصرّح بكل دخلها مهما كانت الحسابات.
- **التعلّم:** يتغير احتمال التدقيق المتصوَّر كل سنة حسب تجربة الشخص وما يراه عند زملائه في القطاع.
- **الاستهداف:** المصلحة لا تعرف الدخل الحقيقي، لكن لديها مؤشر خارجي غير دقيق (مثل الإيداعات البنكية).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

SECTORS = {
    # القطاع: (حصة السكان, نسبة من يمكنهم الإخفاء بسهولة, أقصى نسبة دخل يمكن إخفاؤها)
    "موظفون برواتب": (0.55, 0.0, 0.05),
    "مهن حرة": (0.15, 1.0, 0.50),
    "تجزئة نقدية": (0.12, 1.0, 0.60),
    "مقاولات": (0.10, 1.0, 0.45),
    "شركات كبرى": (0.08, 1.0, 0.15),
}


@dataclass(frozen=True)
class TaxPolicy:
    tax_rate: float = 0.20          # نسبة الضريبة t
    penalty: float = 1.5            # الغرامة f كمضاعف للضريبة المتهرَّب منها
    audit_rate: float = 0.03        # نسبة الملفات المدققة سنوياً
    targeting: float = 0.5          # حصة التدقيق الموجّه بالمخاطر (والباقي عشوائي)
    detection: float = 0.8          # احتمال أن يكشف التدقيق التهرب فعلاً
    signal_noise: float = 0.35      # ضوضاء المؤشر الخارجي (كلما قلّت كان الاستهداف أدق)


@dataclass(frozen=True)
class Population:
    sector: np.ndarray
    income: np.ndarray
    rho: np.ndarray            # النفور من المخاطرة (CRRA)
    moral: np.ndarray          # شدة الكلفة الأخلاقية m
    honest: np.ndarray         # يصرّح بكل شيء دائماً
    max_hidden: np.ndarray     # أقصى نسبة يمكن إخفاؤها (الفرصة)

    def __len__(self) -> int:
        return len(self.income)


def generate_population(n: int = 5000, honest_share: float = 0.3, seed: int = 0) -> Population:
    rng = np.random.default_rng(seed)
    names = list(SECTORS)
    weights = np.array([SECTORS[s][0] for s in names])
    sector = rng.choice(len(names), size=n, p=weights / weights.sum())
    can_hide = np.array([SECTORS[s][1] for s in names])[sector]
    cap = np.array([SECTORS[s][2] for s in names])[sector]
    income_scale = np.array([1.0, 1.4, 0.9, 1.3, 6.0])[sector]
    return Population(
        sector=np.array(names, dtype=object)[sector],
        income=np.round(income_scale * rng.lognormal(np.log(120_000), 0.6, n), -2),
        rho=rng.uniform(0.8, 3.5, n),
        moral=rng.lognormal(np.log(0.25), 0.9, n),
        honest=rng.random(n) < honest_share,
        max_hidden=np.where(rng.random(n) < np.maximum(can_hide, 0.2), cap, 0.0),
    )


def _crra(w: np.ndarray, rho: np.ndarray) -> np.ndarray:
    w = np.maximum(w, 1e-6)
    rho = np.broadcast_to(rho, w.shape)
    near_log = np.abs(rho - 1) < 1e-9
    safe_rho = np.where(near_log, 2.0, rho)
    return np.where(near_log, np.log(w), w ** (1 - safe_rho) / (1 - safe_rho))


def optimal_declaration(p, rho, max_hidden, tax_rate: float, penalty: float, moral=0.0,
                        grid: int = 51) -> np.ndarray:
    """نسبة الدخل المصرّح بها التي تعظّم المنفعة المتوقعة. الاختيار لا يعتمد على حجم الدخل (CRRA)."""
    p, rho, max_hidden = (np.asarray(x, dtype=float)[:, None] for x in (p, rho, max_hidden))
    moral = np.broadcast_to(np.asarray(moral, dtype=float), p.shape[:1])[:, None]
    d = 1 - max_hidden * np.linspace(0, 1, grid)[None, :]  # من 1 (صريح) إلى 1 - أقصى إخفاء
    w1 = 1 - tax_rate * d
    w2 = 1 - tax_rate - penalty * tax_rate * (1 - d)
    eu = (1 - p) * _crra(w1, rho) + p * _crra(w2, rho) - moral * (1 - d) ** 2
    return d[np.arange(len(d)), eu.argmax(axis=1)]


def simulate(pop: Population, policy: TaxPolicy, years: int = 10, seed: int = 0,
             learning: float = 0.3) -> tuple[pd.DataFrame, pd.DataFrame]:
    """يعيد (مؤشرات سنوية, حالة كل شخص في آخر سنة)."""
    rng = np.random.default_rng(seed)
    n = len(pop)
    # الناس يخطئون في تقدير احتمال التدقيق؛ كثيرون يبالغون فيه
    belief = np.clip(policy.audit_rate * rng.lognormal(0.3, 0.8, n), 0.001, 0.9)
    sectors = pd.Series(pop.sector)
    rows = []
    for year in range(1, years + 1):
        frac = optimal_declaration(belief, pop.rho, pop.max_hidden, policy.tax_rate, policy.penalty, pop.moral)
        frac = np.where(pop.honest, 1.0, frac)
        declared = pop.income * frac
        hidden = pop.income - declared

        # التدقيق: جزء موجّه بأعلى درجات المخاطر، والباقي عشوائي
        n_audit = int(round(policy.audit_rate * n))
        n_target = int(round(policy.targeting * n_audit))
        signal = pop.income * rng.lognormal(0, policy.signal_noise, n)  # ما تراه المصلحة
        risk = 1 - declared / signal
        audited = np.zeros(n, dtype=bool)
        audited[np.argsort(-risk)[:n_target]] = True
        rest = np.flatnonzero(~audited)
        audited[rng.choice(rest, size=min(n_audit - n_target, len(rest)), replace=False)] = True
        caught = audited & (hidden > 0) & (rng.random(n) < policy.detection)

        evaded_tax = policy.tax_rate * hidden
        recovered = np.where(caught, evaded_tax * (1 + policy.penalty), 0.0)
        rows.append({
            "year": year,
            "compliance": float(np.mean(hidden <= 1e-9)),
            "evasion_rate": float(hidden.sum() / pop.income.sum()),
            "tax_due": float(policy.tax_rate * pop.income.sum()),
            "tax_declared": float(policy.tax_rate * declared.sum()),
            "tax_gap": float(evaded_tax.sum()),
            "recovered": float(recovered.sum()),
            "audits": int(audited.sum()),
            "hit_rate": float(caught.sum() / max(audited.sum(), 1)),
            "perceived_audit": float(belief.mean()),
        })

        # تحديث التصورات: من دُقِّق عليه يرفع تقديره، والبقية تتأثر بما يرونه في قطاعهم
        peer = pd.Series(audited).groupby(sectors).transform("mean").to_numpy()
        observed = np.where(audited, 1.0, 0.5 * policy.audit_rate + 0.5 * peer)
        belief = np.clip((1 - learning) * belief + learning * observed, 0.001, 0.9)

    people = pd.DataFrame({
        "sector": pop.sector, "income": pop.income, "declared_share": frac,
        "honest": pop.honest, "audited_last_year": audited, "caught_last_year": caught,
        "perceived_audit": belief,
    })
    return pd.DataFrame(rows), people


def policy_sweep(pop: Population, base: TaxPolicy, audit_rates, penalties, years: int = 8,
                 seed: int = 0) -> pd.DataFrame:
    """شبكة سيناريوهات: الفجوة الضريبية النهائية لكل مزيج من نسبة التدقيق والغرامة."""
    out = []
    for a in audit_rates:
        for f in penalties:
            policy = TaxPolicy(**{**base.__dict__, "audit_rate": a, "penalty": f})
            yearly, _ = simulate(pop, policy, years, seed)
            last = yearly.iloc[-1]
            out.append({"audit_rate": a, "penalty": f, "tax_gap_share": last.tax_gap / last.tax_due,
                        "compliance": last.compliance})
    return pd.DataFrame(out)
