"""جامع البيانات: يجلب عدة رموز بالتوازي (asyncio) ويكتب الجديد فقط في المخزن."""
from __future__ import annotations

import asyncio
from dataclasses import dataclass

import pandas as pd

from .sources import PriceSource
from .store import TimeSeriesStore


@dataclass
class CollectResult:
    symbol: str
    rows: int = 0
    error: str | None = None


async def _collect_one(source, symbol, start, end, store, sem) -> CollectResult:
    async with sem:
        try:
            start, end = pd.Timestamp(start), pd.Timestamp(end)
            stored = store.date_range(symbol)
            # تحديث تزايدي: إذا كان أول النطاق محفوظاً نجلب فقط ما بعد آخر تاريخ محفوظ
            if stored is not None and stored[0] <= start:
                start = max(start, stored[1] + pd.Timedelta(days=1))
            if start > end:
                return CollectResult(symbol)
            df = await asyncio.to_thread(source.fetch, symbol, start, end)
            return CollectResult(symbol, rows=store.write(symbol, df))
        except Exception as exc:  # خطأ رمز واحد لا يوقف بقية الرموز
            return CollectResult(symbol, error=f"{type(exc).__name__}: {exc}")


async def collect_async(source: PriceSource, symbols, start, end, store: TimeSeriesStore,
                        concurrency: int = 4) -> list[CollectResult]:
    sem = asyncio.Semaphore(concurrency)
    return await asyncio.gather(*(_collect_one(source, s, start, end, store, sem) for s in symbols))


def collect(source: PriceSource, symbols, start, end, store: TimeSeriesStore,
            concurrency: int = 4) -> list[CollectResult]:
    """نسخة متزامنة للاستخدام من سطر الأوامر أو من Streamlit."""
    return asyncio.run(collect_async(source, symbols, start, end, store, concurrency))
