"""Small shared helpers (no Streamlit imports here)."""
from __future__ import annotations

import hashlib

import numpy as np
import pandas as pd

from utils.config import DISPLAY_NAMES

UNASSIGNED = "(Unassigned)"


def is_text(s: pd.Series) -> bool:
    return pd.api.types.is_object_dtype(s) or pd.api.types.is_string_dtype(s)


def blank_to_label(s: pd.Series, label: str = UNASSIGNED) -> pd.Series:
    if not is_text(s):
        return s
    return s.fillna("").astype(str).replace("", label)


def safe_div(a: float, b: float) -> float:
    return float(a) / float(b) if b else np.nan


def pct(x: float, digits: int = 1) -> str:
    return "—" if x is None or pd.isna(x) else f"{x * 100:.{digits}f}%"


def fmt_num(x, digits: int = 1) -> str:
    if x is None or pd.isna(x):
        return "—"
    if float(x).is_integer():
        return f"{int(x):,}"
    return f"{x:,.{digits}f}"


def df_fingerprint(df: pd.DataFrame) -> str:
    """Stable hash of a DataFrame's content (used as a cache token)."""
    h = hashlib.md5(pd.util.hash_pandas_object(df.astype(str), index=True).values.tobytes())
    return h.hexdigest()[:16]


def display_df(df: pd.DataFrame) -> pd.DataFrame:
    """Rename canonical/derived columns to human-friendly headers."""
    return df.rename(columns={c: DISPLAY_NAMES.get(c, c.replace("_", " ").title())
                              for c in df.columns})
