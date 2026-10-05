"""مقاييس الأسعار والعوائد الأساسية (المرحلة 2 ستضيف VaR و CVaR واختبارات الضغط)."""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def simple_returns(prices: pd.DataFrame | pd.Series):
    return prices.pct_change().iloc[1:]


def log_returns(prices: pd.DataFrame | pd.Series):
    return np.log(prices / prices.shift(1)).iloc[1:]


def rebase(prices: pd.DataFrame, base: float = 100.0) -> pd.DataFrame:
    """توحيد بداية كل سلسلة عند 100 لتُقارن الأصول على محور واحد."""
    return prices / prices.bfill().iloc[0] * base


def annualized_volatility(returns):
    return returns.std(ddof=1) * np.sqrt(TRADING_DAYS)


def rolling_volatility(returns, window: int = 21):
    return returns.rolling(window).std(ddof=1) * np.sqrt(TRADING_DAYS)


def drawdown(prices):
    """نسبة الانخفاض عن أعلى قمة سابقة (صفر أو سالب)."""
    return prices / prices.cummax() - 1


def max_drawdown(prices):
    return drawdown(prices).min()


def cagr(prices: pd.Series) -> float:
    prices = prices.dropna()
    if len(prices) < 2:
        return float("nan")
    years = (prices.index[-1] - prices.index[0]).days / 365.25
    return (prices.iloc[-1] / prices.iloc[0]) ** (1 / years) - 1 if years > 0 else float("nan")


def summary(prices: pd.DataFrame) -> pd.DataFrame:
    """جدول ملخص لكل أصل: العائد الكلي، العائد السنوي المركب، التذبذب، أقصى تراجع، أسوأ وأفضل يوم."""
    rets = simple_returns(prices)
    vol = annualized_volatility(rets)
    growth = prices.apply(cagr)
    return pd.DataFrame({
        "last_price": prices.ffill().iloc[-1],
        "total_return": prices.ffill().iloc[-1] / prices.bfill().iloc[0] - 1,
        "cagr": growth,
        "volatility": vol,
        "sharpe": growth / vol,  # بافتراض عائد خالٍ من المخاطر = 0
        "max_drawdown": prices.apply(max_drawdown),
        "worst_day": rets.min(),
        "best_day": rets.max(),
    })
