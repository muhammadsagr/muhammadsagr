"""مصادر البيانات. كل مصدر يعيد DataFrame فهرسه تواريخ وأعمدته open/high/low/close/volume.

- SyntheticSource: بيانات تجريبية واقعية الشكل (ليست أسعاراً حقيقية) للتطوير والتعلّم.
- CSVSource: ملفات CSV تنزّلها بنفسك من أي موقع (Yahoo Finance، Stooq، تداول...).
"""
from __future__ import annotations

import zlib
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

import numpy as np
import pandas as pd

from .store import COLUMNS


class PriceSource(Protocol):
    name: str

    def fetch(self, symbol: str, start, end) -> pd.DataFrame: ...


@dataclass(frozen=True)
class AssetSpec:
    label: str     # الاسم المعروض
    price: float   # سعر البداية
    drift: float   # العائد السنوي المتوقع
    vol: float     # التذبذب السنوي
    beta: float    # الحساسية لعامل السوق المشترك


# أصول تجريبية بأسماء توضيحية — الأرقام مُولَّدة وليست بيانات السوق الحقيقية
SYNTHETIC_UNIVERSE: dict[str, AssetSpec] = {
    "ENERGY":  AssetSpec("طاقة (تجريبي)", 30.0, 0.06, 0.22, 0.9),
    "BANK":    AssetSpec("بنوك (تجريبي)", 80.0, 0.09, 0.25, 1.1),
    "TELECOM": AssetSpec("اتصالات (تجريبي)", 40.0, 0.05, 0.18, 0.7),
    "PETCHEM": AssetSpec("بتروكيماويات (تجريبي)", 70.0, 0.04, 0.30, 1.2),
    "INDEX":   AssetSpec("مؤشر السوق (تجريبي)", 11000.0, 0.07, 0.16, 1.0),
    "GOLD":    AssetSpec("ذهب (تجريبي)", 2000.0, 0.05, 0.14, -0.1),
}

_ORIGIN = pd.Timestamp("2015-01-01")  # بداية ثابتة كي تكون السلسلة متسقة مهما كان النطاق المطلوب


class SyntheticSource:
    """حركة براونية هندسية مع عامل سوق مشترك (ارتباط) وقفزات نادرة (صدمات)."""

    name = "synthetic"

    def __init__(self, seed: int = 1):
        self.seed = seed

    def _stream(self, *key) -> np.random.Generator:
        # مولّد مستقل لكل كمية: أول n قيمة لا تتغير مهما طال النطاق، فيبقى سعر اليوم ثابتاً
        return np.random.default_rng([self.seed, *key])

    def _market(self, n: int) -> np.ndarray:
        shocks = self._stream(0).standard_normal(n)
        # فترات تذبذب مرتفع (أنظمة سوق) لتبدو البيانات أقرب للواقع
        regime = np.where(self._stream(1).random(n) < 0.005, 2.0, 1.0)
        regime = pd.Series(regime).rolling(20, min_periods=1).max().to_numpy()
        return shocks * regime

    def fetch(self, symbol: str, start, end) -> pd.DataFrame:
        if symbol not in SYNTHETIC_UNIVERSE:
            raise KeyError(f"رمز غير موجود في البيانات التجريبية: {symbol}")
        spec = SYNTHETIC_UNIVERSE[symbol]
        end = pd.Timestamp(end).normalize()
        dates = pd.bdate_range(_ORIGIN, end)
        n = len(dates)
        key = zlib.crc32(symbol.encode())

        def rng(i: int) -> np.random.Generator:
            return self._stream(key, i)

        dt = 1 / 252
        daily_vol = spec.vol * np.sqrt(dt)
        market = self._market(n)
        load = 0.6 * spec.beta  # وزن عامل السوق؛ الباقي حركة خاصة بالأصل
        z = load * market + np.sqrt(1 - load**2) * rng(0).standard_normal(n)
        jump_p, jump_mean = 0.004, -0.03
        jumps = np.where(rng(1).random(n) < jump_p, rng(2).normal(jump_mean, 0.04, n), 0.0)
        # نطرح متوسط القفزات من الاتجاه كي يبقى العائد المتوقع قريباً من drift
        log_ret = (spec.drift - 0.5 * spec.vol**2) * dt - jump_p * jump_mean + daily_vol * z + jumps
        log_ret[0] = 0.0
        close = spec.price * np.exp(np.cumsum(log_ret))

        open_ = np.r_[close[0], close[:-1]] * (1 + rng(3).normal(0, daily_vol / 4, n))
        spread = np.abs(rng(4).normal(0, daily_vol / 2, n))
        high = np.maximum(open_, close) * (1 + spread)
        low = np.minimum(open_, close) * (1 - spread)
        volume = np.round(1e6 * np.exp(rng(5).normal(0, 0.3, n)) * (1 + 20 * np.abs(log_ret)))

        df = pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=pd.DatetimeIndex(dates, name="date"),
        )
        return df.loc[pd.Timestamp(start):end]


class CSVSource:
    """يقرأ <المجلد>/<الرمز>.csv بأعمدة Date, Open, High, Low, Close, Volume (أي حالة أحرف).
    إذا وُجد عمود Adj Close يُستخدم بدل Close (يأخذ توزيعات الأرباح والتجزئة في الحسبان).
    """

    name = "csv"

    def __init__(self, folder: str | Path):
        self.folder = Path(folder)

    def available(self) -> list[str]:
        return sorted(p.stem for p in self.folder.glob("*.csv"))

    def fetch(self, symbol: str, start, end) -> pd.DataFrame:
        raw = pd.read_csv(self.folder / f"{symbol}.csv")
        raw.columns = [c.strip().lower().replace(" ", "_") for c in raw.columns]
        if "adj_close" in raw.columns:
            ratio = raw["adj_close"] / raw["close"]
            for col in ("open", "high", "low"):
                if col in raw.columns:
                    raw[col] = raw[col] * ratio
            raw["close"] = raw["adj_close"]
        if "close" not in raw.columns or "date" not in raw.columns:
            raise ValueError(f"{symbol}.csv يجب أن يحتوي عمودي Date و Close على الأقل")
        for col in ("open", "high", "low"):
            if col not in raw.columns:
                raw[col] = raw["close"]
        if "volume" not in raw.columns:
            raw["volume"] = 0.0
        df = raw.assign(date=pd.to_datetime(raw["date"])).set_index("date").sort_index()
        df = df[COLUMNS].apply(pd.to_numeric, errors="coerce").dropna(subset=["close"])
        df = df[~df.index.duplicated(keep="last")]
        return df.loc[pd.Timestamp(start):pd.Timestamp(end)]
