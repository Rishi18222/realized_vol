"""Tenor-matched remaining variance: IV^2 * T vs forecast_RV^2 * T."""

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
    implied_remaining_var: float = float("nan")
    expected_remaining_var: float = float("nan")
    t_hold: float = float("nan")
    n_sessions: int = 0
    method: str = ""
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


def session_days_from_panel(panel: pd.DataFrame) -> pd.DatetimeIndex:
    """Unique session dates on the native hourly tape. Not 5-minute."""
    df = panel.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return pd.DatetimeIndex(sorted(df["timestamp"].dt.normalize().unique()))


def trade_horizon(ts, book: str, expiry: str) -> pd.Timestamp:
    """Holding horizon: index Monday roll / next Tuesday; stocks to configured exit."""
    asof = pd.Timestamp(ts).normalize()
    exp = pd.Timestamp(expiry).normalize()
    if book == "index":
        roll = asof + pd.Timedelta(days=7)
        return min(roll, exp)
    return exp - pd.Timedelta(days=int(C.STOCK_EXIT_DTE))


def trading_sessions_to_horizon(
    session_days,
    asof,
    horizon,
    *,
    calendar_frac: float | None = None,
) -> tuple[int, str]:
    """Remaining trading sessions (asof, horizon]. Tape count, else 5/7 of calendar DTE.

    Example: 10 calendar days → round(10 * 5/7) = 7 trading days when the tape
    does not cover the horizon.
    """
    frac = C.CALENDAR_TRADING_FRAC if calendar_frac is None else float(calendar_frac)
    a = pd.Timestamp(asof).normalize()
    b = pd.Timestamp(horizon).normalize()
    cal = int((b - a).days)
    if cal <= 0:
        return 0, "horizon_not_after_asof"
    days = pd.DatetimeIndex([])
    if session_days is not None and len(session_days):
        days = pd.DatetimeIndex(pd.to_datetime(session_days)).normalize().unique().sort_values()
    inside = days[(days > a) & (days <= b)] if len(days) else pd.DatetimeIndex([])
    tape_end = days.max() if len(days) else a
    if len(inside) and b <= tape_end:
        return int(len(inside)), "tape"
    fallback = max(int(round(cal * frac)), 1)
    if len(inside) == 0:
        return fallback, "calendar_5_7"
    extra_cal = max(int((b - tape_end).days), 0)
    n = int(len(inside) + round(extra_cal * frac))
    return max(n, 1), "tape+calendar_5_7"


def remaining_t_years(n_sessions: int) -> float:
    """Remaining trading time in years: n / 252. Same T on IV and RV."""
    return max(int(n_sessions), 0) / float(C.TRADING_DAYS)


def rv_nd_ann(daily_close: pd.Series, asof, n: int) -> float:
    """Annualized RV from n daily log returns, PIT as-of. Lookback = n sessions."""
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
    """HAR mix of 5/20/60/120-day RV. Used only as a forecast of remaining tenor."""
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


def tenor_forecast_rv(
    daily_close: pd.Series,
    asof,
    n_sessions: int,
) -> tuple[float, list[int], list[float], str]:
    """Forecast remaining-tenor RV.

    Comparison lookback is n remaining trading sessions (matched tenor), not
    20/60/120 as the comparison window. HAR 5/20/60/120 may blend in as a
    forecast of that same n-day tenor when those windows exist.
    """
    n = int(n_sessions)
    if n < 1:
        return float("nan"), [], [], "n_sessions<1"
    matched = rv_nd_ann(daily_close, asof, n)
    har, hw, hwt = forecast_rv_ann(daily_close, asof)
    mw = float(C.MATCHED_VAR_WEIGHT)
    hwgt = float(C.HAR_VAR_WEIGHT)
    if np.isfinite(matched) and matched > 0 and np.isfinite(har) and har > 0:
        var_f = mw * float(matched) ** 2 + hwgt * float(har) ** 2
        windows = [n] + [f"har{k}" for k in hw]
        weights = [mw] + [hwgt * w for w in hwt]
        return float(np.sqrt(max(var_f, 0.0))), windows, weights, "matched+har_forecast"
    if np.isfinite(matched) and matched > 0:
        return float(matched), [n], [1.0], "matched_lookback"
    if np.isfinite(har) and har > 0:
        return float(har), hw, hwt, f"har_forecast_of_{n}d"
    return float("nan"), [], [], "no remaining-tenor RV"


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
    windows: list,
    weights_used: list[float],
    *,
    t_hold: float,
    t_opt: float,
    n_sessions: int,
    method: str = "",
) -> VRPSignal:
    """Remaining-variance test. Same T on both sides.

    implied_remaining_var = IV^2 * T
    expected_remaining_var = forecast_RV^2 * T
    T = remaining trading years to the trade horizon (n/252).

    Short: implied remaining > expected remaining, after costs/buffers.
    Long: expected remaining > implied remaining, after costs/buffers.
    Near-expiry longs with a tiny annualized vol-pt gap fail this remaining-T test.
    """
    out = VRPSignal(
        side=None,
        iv=float(iv) if np.isfinite(iv) else float("nan"),
        rv_forecast=float(rv_forecast) if np.isfinite(rv_forecast) else float("nan"),
        vrp_var=float("nan"),
        vrp_pts=float("nan"),
        windows=list(windows),
        weights_used=list(weights_used),
        t_hold=float(t_hold) if np.isfinite(t_hold) else float("nan"),
        n_sessions=int(n_sessions),
        method=str(method),
    )
    if not np.isfinite(iv) or not np.isfinite(rv_forecast) or rv_forecast <= 0 or iv <= 0:
        out.reason = "no IV/RV forecast"
        return out
    if not np.isfinite(t_hold) or t_hold <= 0 or int(n_sessions) < 2:
        out.reason = f"horizon too short n={n_sessions} T={t_hold}"
        return out
    if not np.isfinite(t_opt) or t_opt <= 0:
        out.reason = "no option tenor T"
        return out
    implied = float(iv) ** 2 * float(t_hold)
    expected = float(rv_forecast) ** 2 * float(t_hold)
    out.implied_remaining_var = implied
    out.expected_remaining_var = expected
    out.vrp_var = implied - expected
    out.vrp_pts = (float(iv) - float(rv_forecast)) * 100.0
    sens = (float(vega_1pct) * 100.0) / (2.0 * float(iv) * float(t_opt))
    edge = float(sens) * float(out.vrp_var) * int(lot)
    cost = roundtrip_cost(premium_1lot)
    hurdle = cost * (1.0 + float(C.COST_BUFFER_MULT))
    out.edge_1lot = edge
    out.cost_1lot = cost
    # Short: implied remaining var covers expected + costs.
    if implied > expected and edge > hurdle:
        out.side = "short"
        out.net_1lot = edge - hurdle
        out.reason = (
            f"short remVar impl {implied:.6g} > exp {expected:.6g} "
            f"n={n_sessions} net {out.net_1lot:,.0f} {method}"
        )
        return out
    # Long: expected remaining realized var covers implied + costs.
    # Tiny negative vol-pt gaps with a few days of T fail here; skip until next session.
    if expected > implied and (-edge) > hurdle:
        out.side = "long"
        out.net_1lot = -edge - hurdle
        out.reason = (
            f"long remVar exp {expected:.6g} > impl {implied:.6g} "
            f"n={n_sessions} net {out.net_1lot:,.0f} {method}"
        )
        return out
    out.net_1lot = abs(edge) - hurdle
    if expected > implied:
        out.reason = (
            f"long remVar exp {expected:.6g} vs impl {implied:.6g} "
            f"n={n_sessions} edge {-edge:,.0f} < hurdle {hurdle:,.0f}"
        )
    elif implied > expected:
        out.reason = (
            f"short remVar impl {implied:.6g} vs exp {expected:.6g} "
            f"n={n_sessions} edge {edge:,.0f} < hurdle {hurdle:,.0f}"
        )
    else:
        out.reason = f"flat remaining var n={n_sessions}"
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
