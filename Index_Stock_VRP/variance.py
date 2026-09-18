"""Implied forward variance vs 5/20/60/120 forecast RV. Long or short vol."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import config as C


@dataclass
class VRPSignal:
    side: str | None
    iv: float
    rv_forecast: float
    vrp_var: float
    vrp_pts: float
    windows: list[int] = field(default_factory=list)
    weights_used: list[float] = field(default_factory=list)
    edge_1lot: float = 0.0
    cost_1lot: float = 0.0
    net_1lot: float = 0.0
    reason: str = ""


def sold_variance(iv: float, t_years: float) -> float:
    return float(iv) ** 2 * max(float(t_years), 0.0)


def hourly_spot(panel: pd.DataFrame) -> pd.Series:
    df = panel.dropna(subset=["spot"]).copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    s = pd.to_numeric(df.set_index("timestamp")["spot"], errors="coerce").dropna().sort_index()
    return s[~s.index.duplicated(keep="last")]


def daily_close_from_hourly(spot: pd.Series) -> pd.Series:
    px = pd.to_numeric(spot, errors="coerce").dropna().sort_index()
    if px.empty:
        return px
    return px.groupby(px.index.normalize()).last().sort_index()


def rv_nd_ann(daily_close: pd.Series, asof, n: int) -> float:
    """Annualized RV from n daily log returns, PIT as-of."""
    px = pd.to_numeric(daily_close, errors="coerce").dropna().sort_index()
    px = px[px.index <= pd.Timestamp(asof).normalize()]
    if len(px) < n + 1:
        return float("nan")
    r = np.log(px / px.shift(1)).dropna().iloc[-int(n) :]
    if len(r) < int(n):
        return float("nan")
    return float(np.sqrt(np.mean(np.square(r.to_numpy())) * C.TRADING_DAYS))


def forecast_rv_ann(
    daily_close: pd.Series,
    asof,
    windows: tuple[int, ...] | None = None,
    weights: tuple[float, ...] | None = None,
) -> tuple[float, list[int], list[float]]:
    """HAR-style forecast: weighted mix of 5/20/60/120-day RV.

    Missing windows (common for 60/120 on a ~180d Groww tape) are dropped
    and remaining weights are renormalized. Nothing is fabricated.
    """
    windows = windows or C.RV_WINDOWS
    weights = weights or C.RV_WEIGHTS
    used_n: list[int] = []
    used_w: list[float] = []
    used_var: list[float] = []
    for n, w in zip(windows, weights):
        rv = rv_nd_ann(daily_close, asof, int(n))
        if not np.isfinite(rv) or rv <= 0:
            continue
        used_n.append(int(n))
        used_w.append(float(w))
        used_var.append(float(rv) ** 2)
    if len(used_n) < int(C.MIN_RV_WINDOWS):
        return float("nan"), used_n, used_w
    w = np.asarray(used_w, dtype=float)
    w = w / w.sum()
    var_f = float(np.dot(w, np.asarray(used_var, dtype=float)))
    return float(np.sqrt(max(var_f, 0.0))), used_n, w.tolist()


def roundtrip_cost(premium_cash: float, slip: float | None = None) -> float:
    from .execution import statutory_opt

    p = abs(float(premium_cash))
    slip = C.SLIPPAGE_FRAC if slip is None else float(slip)
    return (
        statutory_opt(p, "sell")["total"]
        + statutory_opt(p, "buy")["total"]
        + 2.0 * slip * p
    )


def vrp_signal(
    iv: float,
    rv_forecast: float,
    vega_1pct: float,
    lot: int,
    premium_1lot: float,
    windows: list[int],
    weights_used: list[float],
) -> VRPSignal:
    """Positive net VRP → short vol. Negative net VRP → long vol. Else flat."""
    out = VRPSignal(
        side=None,
        iv=float(iv) if np.isfinite(iv) else float("nan"),
        rv_forecast=float(rv_forecast) if np.isfinite(rv_forecast) else float("nan"),
        vrp_var=float("nan"),
        vrp_pts=float("nan"),
        windows=list(windows),
        weights_used=list(weights_used),
    )
    if not np.isfinite(iv) or not np.isfinite(rv_forecast) or rv_forecast <= 0 or iv <= 0:
        out.reason = "no IV/RV forecast"
        return out
    out.vrp_var = float(iv) ** 2 - float(rv_forecast) ** 2
    out.vrp_pts = (float(iv) - float(rv_forecast)) * 100.0
    if abs(out.vrp_pts) < float(C.MIN_VRP_PTS):
        out.reason = f"|VRP| {out.vrp_pts:.2f}pt < {C.MIN_VRP_PTS}"
        return out
    edge = float(vega_1pct) * out.vrp_pts * int(lot)
    cost = roundtrip_cost(premium_1lot)
    hurdle = cost * (1.0 + float(C.COST_BUFFER_MULT))
    out.edge_1lot = edge
    out.cost_1lot = cost
    if edge > hurdle:
        out.side = "short"
        out.net_1lot = edge - hurdle
        out.reason = f"short VRP {out.vrp_pts:.2f}pt net {out.net_1lot:,.0f} windows={windows}"
        return out
    if -edge > hurdle:
        out.side = "long"
        out.net_1lot = -edge - hurdle
        out.reason = f"long VRP {out.vrp_pts:.2f}pt net {out.net_1lot:,.0f} windows={windows}"
        return out
    out.net_1lot = abs(edge) - hurdle
    out.reason = f"VRP {out.vrp_pts:.2f}pt edge {edge:,.0f} < hurdle {hurdle:,.0f}"
    return out


def budget_exhausted(path_real_var: float, sold_var: float) -> bool:
    if not np.isfinite(path_real_var) or not np.isfinite(sold_var) or sold_var <= 0:
        return False
    return float(path_real_var) >= float(sold_var)


def crush_take(iv_now: float, t_now: float, sold_var: float, path_real_var: float, frac: float | None = None) -> bool:
    frac = C.CRUSH_FRAC if frac is None else float(frac)
    if not np.isfinite(iv_now) or not np.isfinite(sold_var) or sold_var <= 0:
        return False
    remaining_impl = sold_variance(iv_now, t_now)
    if remaining_impl > frac * sold_var:
        return False
    if np.isfinite(path_real_var) and path_real_var >= 0.5 * sold_var:
        return False
    return True


def running_hot_ratio(path_real_var: float, elapsed_t: float, sold_var: float, t_entry: float) -> float:
    if not np.isfinite(path_real_var) or not np.isfinite(sold_var) or sold_var <= 0:
        return float("nan")
    if elapsed_t <= 1e-12 or t_entry <= 1e-12:
        return float("nan")
    sold_rate = sold_var / t_entry
    real_rate = path_real_var / elapsed_t
    if sold_rate <= 0:
        return float("nan")
    return float(real_rate / sold_rate)


def is_running_hot(
    path_real_var: float,
    elapsed_t: float,
    sold_var: float,
    t_entry: float,
    mult: float | None = None,
) -> bool:
    mult = C.RUNNING_HOT_MULT if mult is None else float(mult)
    min_elapsed = float(C.RUNNING_HOT_MIN_HOURS) / (365.25 * 24.0)
    if elapsed_t < min_elapsed:
        return False
    r = running_hot_ratio(path_real_var, elapsed_t, sold_var, t_entry)
    return bool(np.isfinite(r) and r >= mult)
