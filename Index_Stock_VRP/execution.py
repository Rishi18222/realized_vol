"""Bid/ask fills when present; otherwise mid ± explicit slippage. Statutory costs at mid."""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import config as C


def mid_from_ohlc(row: pd.Series | None) -> float | None:
    if row is None:
        return None
    for col in ("close", "mid", "px"):
        if col in row.index and pd.notna(row[col]):
            return float(row[col])
    return None


def row_at_hour(df: pd.DataFrame | None, ts: pd.Timestamp) -> pd.Series | None:
    if df is None or df.empty:
        return None
    frame = df.copy()
    if "timestamp" in frame.columns:
        frame = frame.set_index(pd.to_datetime(frame["timestamp"]))
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    ts = pd.Timestamp(ts).tz_localize(None)
    day = ts.normalize()
    hour = int(ts.hour)
    same = frame[(frame.index.normalize() == day) & (frame.index.hour == hour)]
    if same.empty:
        return None
    return same.iloc[-1]


def row_asof(df: pd.DataFrame | None, ts: pd.Timestamp) -> pd.Series | None:
    if df is None or df.empty:
        return None
    frame = df.copy()
    if "timestamp" in frame.columns:
        frame = frame.set_index(pd.to_datetime(frame["timestamp"]))
    frame.index = pd.to_datetime(frame.index).tz_localize(None)
    ts = pd.Timestamp(ts).tz_localize(None)
    prior = frame[frame.index <= ts]
    if prior.empty:
        return None
    return prior.iloc[-1]


def _bid_ask(row: pd.Series | None) -> tuple[float | None, float | None, float | None]:
    if row is None:
        return None, None, None
    mid = mid_from_ohlc(row)
    bid = float(row["bid"]) if "bid" in row.index and pd.notna(row.get("bid")) else None
    ask = float(row["ask"]) if "ask" in row.index and pd.notna(row.get("ask")) else None
    return bid, ask, mid


def fill_price(
    row: pd.Series | None,
    *,
    side: str,
    slippage: float = C.SLIPPAGE_FRAC,
    use_bid_ask: bool = C.USE_BID_ASK,
) -> tuple[float | None, str]:
    """Return (fill, source). Sell lifts bid; buy pays ask. Else mid ± slippage."""
    bid, ask, mid = _bid_ask(row)
    sell = side in ("sell", "short")
    if use_bid_ask and sell and bid is not None and bid > 0:
        return bid, "bid"
    if use_bid_ask and (not sell) and ask is not None and ask > 0:
        return ask, "ask"
    if mid is None or not np.isfinite(mid) or mid <= 0:
        return None, "missing"
    slip = max(float(slippage), 0.0)
    px = mid * (1.0 - slip) if sell else mid * (1.0 + slip)
    return float(px), "mid+slip"


def statutory_opt(premium_cash: float, side: str) -> dict[str, float]:
    p = abs(float(premium_cash))
    stt = C.STT_OPT_SELL * p if side in ("sell", "short") else 0.0
    stamp = C.STAMP_OPT_BUY * p if side in ("buy", "long") else 0.0
    nse = C.NSE_OPT * p
    sebi = C.SEBI * p
    gst = C.GST * (nse + sebi)
    return dict(stt=stt, stamp=stamp, nse=nse, sebi=sebi, gst=gst, total=stt + stamp + nse + sebi + gst)


def hedge_cost(notional: float, d_units: float) -> float:
    """Approximate F&O futures/SSF cost on the traded notional."""
    n = abs(float(notional))
    if n <= 0 or abs(d_units) < 1e-9:
        return 0.0
    if d_units > 0:
        return C.FUT_STAMP_BUY * n
    return C.FUT_STT_SELL * n
