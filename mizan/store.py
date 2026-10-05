"""مخزن سلاسل زمنية مكتوب من الصفر.

كل رمز له ملف ثنائي خاص به يُكتب بطريقة الإلحاق فقط (append-only):
- رأس الملف: 4 بايت ثابتة (MAGIC) للتحقق من نوع الملف.
- كل سجل حجمه ثابت (48 بايت): اليوم + الافتتاح/الأعلى/الأدنى/الإغلاق/الحجم + CRC32.
- الـ CRC يكشف السجل المقطوع إذا انقطع التيار أثناء الكتابة، فيُحذف عند الفتح (استرداد).
- الكتابة فوق يوم موجود = إلحاق سجل جديد، والقراءة تأخذ آخر نسخة (last-write-wins).
- compact() يعيد كتابة الملف مرتباً وبدون تكرار، ويستبدله بشكل ذري.
"""
from __future__ import annotations

import os
import re
import struct
import zlib
from bisect import bisect_left, bisect_right
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

MAGIC = b"MZN1"
_BODY = struct.Struct("<i5d")  # اليوم (أيام منذ 1970) + 5 أرقام عشرية
_CRC = struct.Struct("<I")
RECORD_SIZE = _BODY.size + _CRC.size
COLUMNS = ["open", "high", "low", "close", "volume"]
_SYMBOL_RE = re.compile(r"^[A-Za-z0-9._^-]{1,32}$")
_EPOCH = date(1970, 1, 1)


class CorruptFileError(Exception):
    """الملف ليس ملف ميزان (رأس غير صحيح)."""


def _to_day(d) -> int:
    return (pd.Timestamp(d).date() - _EPOCH).days


def _from_day(n: int) -> pd.Timestamp:
    return pd.Timestamp(_EPOCH) + pd.Timedelta(days=n)


def _pack(day: int, values) -> bytes:
    body = _BODY.pack(day, *map(float, values))
    return body + _CRC.pack(zlib.crc32(body))


class TimeSeriesStore:
    def __init__(self, root: str | os.PathLike):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        # ذاكرة مؤقتة لكل رمز: (أيام مرتبة, مصفوفة القيم)
        self._cache: dict[str, tuple[list[int], np.ndarray]] = {}

    # ------------------------------------------------------------ أدوات داخلية
    def _path(self, symbol: str) -> Path:
        if not _SYMBOL_RE.match(symbol):
            raise ValueError(f"رمز غير صالح: {symbol!r}")
        return self.root / f"{symbol}.mzn"

    def _load(self, symbol: str) -> tuple[list[int], np.ndarray]:
        if symbol in self._cache:
            return self._cache[symbol]
        path = self._path(symbol)
        latest: dict[int, tuple] = {}
        if path.exists():
            data = path.read_bytes()
            if data[:4] != MAGIC:
                raise CorruptFileError(f"{path} ليس ملف ميزان")
            valid_end = 4
            for off in range(4, len(data) - RECORD_SIZE + 1, RECORD_SIZE):
                body = data[off:off + _BODY.size]
                (crc,) = _CRC.unpack_from(data, off + _BODY.size)
                if zlib.crc32(body) != crc:
                    break  # سجل تالف: نتوقف ونعتبر ما بعده غير موثوق
                day, *values = _BODY.unpack(body)
                latest[day] = values
                valid_end = off + RECORD_SIZE
            if valid_end != len(data):  # ذيل مقطوع أو تالف: نقصّه (استرداد)
                with open(path, "r+b") as f:
                    f.truncate(valid_end)
        days = sorted(latest)
        values = np.array([latest[d] for d in days], dtype=float).reshape(-1, len(COLUMNS))
        self._cache[symbol] = (days, values)
        return days, values

    # ------------------------------------------------------------ الواجهة العامة
    def symbols(self) -> list[str]:
        return sorted(p.stem for p in self.root.glob("*.mzn"))

    def write(self, symbol: str, df: pd.DataFrame) -> int:
        """إلحاق صفوف (فهرسها تواريخ، وأعمدتها COLUMNS). يعيد عدد الصفوف المكتوبة."""
        if df.empty:
            return 0
        missing = set(COLUMNS) - set(df.columns)
        if missing:
            raise ValueError(f"أعمدة ناقصة: {sorted(missing)}")
        path = self._path(symbol)
        chunks = [] if path.exists() else [MAGIC]
        chunks += [_pack(_to_day(idx), row) for idx, row in zip(df.index, df[COLUMNS].to_numpy())]
        with open(path, "ab") as f:
            f.write(b"".join(chunks))
            f.flush()
            os.fsync(f.fileno())
        self._cache.pop(symbol, None)
        return len(df)

    def read(self, symbol: str, start=None, end=None) -> pd.DataFrame:
        """قراءة نطاق تواريخ (شامل للطرفين) باستخدام البحث الثنائي."""
        days, values = self._load(symbol)
        lo = bisect_left(days, _to_day(start)) if start is not None else 0
        hi = bisect_right(days, _to_day(end)) if end is not None else len(days)
        index = pd.DatetimeIndex([_from_day(d) for d in days[lo:hi]], name="date")
        return pd.DataFrame(values[lo:hi], index=index, columns=COLUMNS)

    def date_range(self, symbol: str) -> tuple[pd.Timestamp, pd.Timestamp] | None:
        """أول وآخر تاريخ محفوظ، أو None إذا لم توجد بيانات."""
        if not self._path(symbol).exists():
            return None
        days, _ = self._load(symbol)
        return (_from_day(days[0]), _from_day(days[-1])) if days else None

    def compact(self, symbol: str) -> None:
        """إعادة كتابة الملف بدون تكرارات، ثم استبداله ذرياً."""
        days, values = self._load(symbol)
        path = self._path(symbol)
        tmp = path.with_suffix(".tmp")
        with open(tmp, "wb") as f:
            f.write(MAGIC + b"".join(_pack(d, v) for d, v in zip(days, values)))
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
