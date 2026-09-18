"""Matched-tenor variance ratio, PIT z-score, remaining-variance budget."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C


def sold_variance(iv: float, t_years: float) -> float:
    """Total variance sold: σ²T, not an 80% remaining-RV shortcut."""
    return float(iv) ** 2 * max(float(t_years), 0.0)


def n_bars_for_tenor(t_years: float) -> int:
    n = int(round(max(float(t_years), 0.0) * C.TRADING_DAYS * C.NATIVE_BARS_PER_DAY))
    return max(n, 2)


def hourly_spot(panel: pd.DataFrame) -> pd.Series:
    df = panel.dropna(subset=["spot"]).copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    s = pd.to_numeric(df.set_index("timestamp")["spot"], errors="coerce").dropna().sort_index()
    return s[~s.index.duplicated(keep="last")]


def matched_tenor_rv_ann(spot: pd.Series, asof, t_years: float) -> float:
    """Annualized RV from native hourly log returns over a window matching tenor T."""
    px = pd.to_numeric(spot, errors="coerce").dropna().sort_index()
    px = px[px.index <= pd.Timestamp(asof)]
    n = n_bars_for_tenor(t_years)
    if len(px) < 3:
        return float("nan")
    r = np.log(px / px.shift(1)).dropna()
    if r.empty:
        return float("nan")
    window = r.iloc[-min(n, len(r)) :]
    bars_year = C.TRADING_DAYS * C.NATIVE_BARS_PER_DAY
    return float(np.sqrt(np.mean(np.square(window.to_numpy())) * bars_year))


def variance_ratio(iv: float, rv_ann: float) -> float:
    """IV² / RV² on annualized vols (decimals)."""
    if not np.isfinite(iv) or not np.isfinite(rv_ann) or rv_ann <= 0:
        return float("nan")
    return (float(iv) ** 2) / (float(rv_ann) ** 2)


def pit_zscore(history: list[float] | np.ndarray, value: float, min_obs: int | None = None) -> float:
    min_obs = C.Z_MIN_OBS if min_obs is None else int(min_obs)
    h = np.asarray([x for x in history if np.isfinite(x)], dtype=float)
    if not np.isfinite(value) or h.size < min_obs:
        return float("nan")
    sd = float(h.std(ddof=1))
    if sd <= 1e-12:
        return 0.0
    return float((value - float(h.mean())) / sd)


def signal_ok(
    ratio: float,
    z: float,
    *,
    ratio_min: float | None = None,
    z_min: float | None = None,
) -> tuple[bool, str]:
    ratio_min = C.VAR_RATIO_MIN if ratio_min is None else float(ratio_min)
    z_min = C.Z_MIN if z_min is None else float(z_min)
    if not np.isfinite(ratio):
        return False, "no var_ratio"
    if ratio < ratio_min:
        return False, f"var_ratio {ratio:.2f}<{ratio_min}"
    if np.isfinite(z) and z < z_min:
        return False, f"z {z:.2f}<{z_min}"
    if np.isfinite(z):
        return True, f"var_ratio {ratio:.2f} z {z:.2f}"
    return True, f"var_ratio {ratio:.2f} z=na (short hist)"


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
    min_hours = float(C.RUNNING_HOT_MIN_HOURS)
    min_elapsed = min_hours / (365.25 * 24.0)
    if elapsed_t < min_elapsed:
        return False
    r = running_hot_ratio(path_real_var, elapsed_t, sold_var, t_entry)
    return bool(np.isfinite(r) and r >= mult)
