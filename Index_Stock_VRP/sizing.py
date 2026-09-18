"""Stress-loss lot sizing for long or short ATM-forward straddles."""

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
    side: str = "short",
    em_mult: float = C.EM_MULT,
) -> float:
    """Worse restress on one straddle lot. Short: 1.75× EM. Long: vol crush."""
    g0 = straddle_unit(spot, k, t, iv)
    sign = 1.0 if side == "long" else -1.0
    worst = 0.0
    if side == "long":
        g1 = straddle_unit(spot, k, t, max(iv * 0.70, 0.05))
        opt = sign * lot * (g1["price"] - g0["price"])
        return float(min(0.0, opt))
    days = max(t * 365.25, 1.0)
    move = expected_move(spot, iv, days) * em_mult
    for s1 in (spot + move, spot - move, max(spot * 0.5, spot - move)):
        if s1 <= 0:
            continue
        g1 = straddle_unit(s1, k, t, iv)
        opt = sign * lot * (g1["price"] - g0["price"])
        fut = 0.0
        if hedge:
            fut = (-g0["delta"] * sign * lot) * (s1 - spot)
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
    side: str = "short",
    capital: float = C.TARGET_CAPITAL,
    stress_frac: float = C.STRESS_FRAC,
    max_lots: int | None = None,
) -> int:
    t = years_to(ts, expiry)
    one = stress_pnl_one_lot(spot, k, t, iv, lot, hedge=hedge, side=side)
    budget = -abs(float(capital) * float(stress_frac))
    cap = C.MAX_LOTS if max_lots is None else int(max_lots)
    if one >= 0 or not np.isfinite(one):
        return 1
    n = int(math.floor(budget / one))
    return int(np.clip(n, 1, cap))
