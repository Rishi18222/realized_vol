"""Variance risk premium signals and remaining-variance exits."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C


def implied_variance(iv: float, t_years: float) -> float:
    return float(iv) ** 2 * max(float(t_years), 0.0)


def realized_variance(log_returns: np.ndarray | list[float]) -> float:
    r = np.asarray(log_returns, dtype=float)
    r = r[np.isfinite(r)]
    if r.size == 0:
        return 0.0
    return float(np.sum(r ** 2))


def rv_nd_pct(daily_close: pd.Series, asof, n: int = C.RV_LOOKBACK_DAYS) -> float:
    px = pd.to_numeric(daily_close, errors="coerce").dropna().sort_index()
    px = px[px.index <= pd.Timestamp(asof).normalize()]
    if len(px) < n + 1:
        return float("nan")
    r = np.log(px / px.shift(1)).dropna().iloc[-n:]
    if len(r) < n:
        return float("nan")
    return float(np.sqrt(np.sum(r.to_numpy() ** 2) / n) * np.sqrt(C.TRADING_DAYS) * 100.0)


def vrp_pts(iv_pct: float, rv_pct: float) -> float:
    if not np.isfinite(iv_pct) or not np.isfinite(rv_pct):
        return float("nan")
    return float(iv_pct) - float(rv_pct)


def signal_ok(iv_pct: float, rv_pct: float, min_pts: float = C.VRP_MIN_PTS) -> tuple[bool, str, float]:
    gap = vrp_pts(iv_pct, rv_pct)
    if not np.isfinite(gap):
        return False, "no VRP", gap
    if gap < min_pts:
        return False, f"VRP {gap:.2f}<{min_pts}", gap
    return True, f"VRP {gap:.2f}", gap


def variance_exhausted(real_var: float, impl_var: float, frac: float = C.VAR_EXIT_FRAC) -> bool:
    if not np.isfinite(real_var) or not np.isfinite(impl_var) or impl_var <= 0:
        return False
    return float(real_var) >= float(frac) * float(impl_var)
