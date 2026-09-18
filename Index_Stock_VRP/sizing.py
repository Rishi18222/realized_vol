"""Stress-loss lot sizing. Approximate short-option + hedge margins."""

from __future__ import annotations

import math

import numpy as np

from . import config as C
from .pricing import expected_move, straddle_unit, years_to


def stress_pnl_one_lot(
    spot: float,
    k: float,
    t: float,
    iv: float,
    lot: int,
    *,
    hedge: bool,
    em_mult: float = C.EM_MULT,
) -> float:
    """Worse of up/down 1.75× expected-move restress on one short ATM-forward straddle lot."""
    g0 = straddle_unit(spot, k, t, iv)
    days = max(t * 365.25, 1.0)
    move = expected_move(spot, iv, days) * em_mult
    worst = 0.0
    for s1 in (spot + move, spot - move, max(spot * 0.5, spot - move)):
        if s1 <= 0:
            continue
        g1 = straddle_unit(s1, k, t, iv)
        opt = lot * (g0["price"] - g1["price"])
        fut = 0.0
        if hedge:
            fut = (-g0["delta"] * lot) * (s1 - spot)
        worst = min(worst, opt + fut)
    return float(worst)


def lots_for_stress(
    spot: float,
    k: float,
    expiry: str,
    ts,
    iv: float,
    lot: int,
    *,
    hedge: bool,
    capital: float = C.TARGET_CAPITAL,
    stress_frac: float = C.STRESS_FRAC,
    max_lots: int = 200,
) -> int:
    t = years_to(ts, expiry)
    one = stress_pnl_one_lot(spot, k, t, iv, lot, hedge=hedge)
    budget = -abs(float(capital) * float(stress_frac))
    if one >= 0 or not np.isfinite(one):
        return 1
    n = int(math.floor(budget / one))
    return int(np.clip(n, 1, max_lots))


def margin_posted(spot: float, lots: int, lot: int, fut_units: float, *, is_index: bool) -> dict[str, float]:
    short_pct = C.MARGIN_SHORT_PCT if is_index else C.MARGIN_STOCK_PCT
    span = short_pct * spot * lot * abs(lots)
    fut_pct = C.MARGIN_FUT_PCT if is_index else C.MARGIN_STOCK_PCT
    fut = fut_pct * spot * abs(fut_units)
    capital = max(span + fut, 0.25 * span)
    return dict(span=span, fut=fut, capital=capital)
