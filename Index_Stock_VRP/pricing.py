"""ATM-forward strike, BS straddle marks, years-to-expiry."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from . import config as C


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def years_to(ts: pd.Timestamp, expiry: str) -> float:
    exp = pd.Timestamp(expiry) + pd.Timedelta(hours=15, minutes=30)
    return max((exp - pd.Timestamp(ts)).total_seconds() / (365.25 * 24 * 3600), 1e-6)


def dte_days(ts: pd.Timestamp, expiry: str) -> int:
    return int((pd.Timestamp(expiry).normalize() - pd.Timestamp(ts).normalize()).days)


def forward_price(spot: float, t: float, r: float = C.RISK_FREE, q: float = C.DIV_YIELD) -> float:
    return float(spot) * math.exp((r - q) * max(float(t), 0.0))


def nearest_strike(strikes: list[float], target: float) -> float:
    if not strikes:
        raise ValueError("no strikes")
    return float(min(strikes, key=lambda k: abs(float(k) - float(target))))


def snap_strike(target: float, step: float) -> float:
    step = float(step) if step and step > 0 else 1.0
    return float(round(float(target) / step) * step)


def atm_forward_strike(
    spot: float,
    t: float,
    *,
    strikes: list[float] | None = None,
    step: float = C.NIFTY_STRIKE_STEP,
    r: float = C.RISK_FREE,
) -> float:
    """Nearest listed strike to the interest-rate forward, not spot."""
    f = forward_price(spot, t, r)
    if strikes:
        return nearest_strike(list(strikes), f)
    return snap_strike(f, step)


def bs_greeks(S: float, K: float, T: float, sigma: float, opt_type: str, r: float = C.RISK_FREE, q: float = C.DIV_YIELD) -> dict[str, float]:
    if T <= 0 or sigma <= 0:
        intrinsic = max(S - K, 0.0) if opt_type == "call" else max(K - S, 0.0)
        return {"price": intrinsic, "delta": 0.0, "gamma": 0.0, "theta": 0.0, "vega": 0.0}
    d1 = (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))
    d2 = d1 - sigma * math.sqrt(T)
    df_r, df_q = math.exp(-r * T), math.exp(-q * T)
    pdf = _norm_pdf(d1)
    gamma = df_q * pdf / (S * sigma * math.sqrt(T))
    vega = S * df_q * pdf * math.sqrt(T) * 0.01
    time_decay = -S * df_q * pdf * sigma / (2.0 * math.sqrt(T))
    if opt_type == "call":
        price = S * df_q * _norm_cdf(d1) - K * df_r * _norm_cdf(d2)
        delta = df_q * _norm_cdf(d1)
        theta_yr = time_decay - r * K * df_r * _norm_cdf(d2) + q * S * df_q * _norm_cdf(d1)
    else:
        price = K * df_r * _norm_cdf(-d2) - S * df_q * _norm_cdf(-d1)
        delta = -df_q * _norm_cdf(-d1)
        theta_yr = time_decay + r * K * df_r * _norm_cdf(-d2) - q * S * df_q * _norm_cdf(-d1)
    return {"price": float(price), "delta": float(delta), "gamma": float(gamma), "theta": float(theta_yr / 365.25), "vega": float(vega)}


def straddle_unit(S: float, K: float, T: float, sigma: float) -> dict[str, float]:
    call = bs_greeks(S, K, T, sigma, "call")
    put = bs_greeks(S, K, T, sigma, "put")
    return {
        "price": float(call["price"] + put["price"]),
        "delta": float(call["delta"] + put["delta"]),
        "gamma": float(call["gamma"] + put["gamma"]),
        "vega": float(call["vega"] + put["vega"]),
        "theta": float(call["theta"] + put["theta"]),
        "ce": float(call["price"]),
        "pe": float(put["price"]),
    }


def expected_move(spot: float, iv: float, days: float) -> float:
    return float(spot) * float(iv) * float(np.sqrt(max(days, 1e-6) / 365.25))
