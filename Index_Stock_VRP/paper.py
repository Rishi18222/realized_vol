"""Paper blotter from the last bar: daily scan, long or short, both books."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import calendar_events as ev
from . import config as C
from . import universe as uni
from . import variance as var
from .engine import _next_monthly, _next_tuesday
from .pricing import atm_forward_strike, straddle_unit, years_to
from .sizing import lots_for_stress
from .source import row_at


def _row_for(src, ts, symbol, book, events, membership) -> dict:
    try:
        panel = src.panel(symbol)
    except Exception as exc:
        return dict(ts=str(ts), book=book, symbol=symbol, action="skip", note=f"no panel {exc.__class__.__name__}")
    r = row_at(panel, ts)
    if r is None or pd.isna(r.get("spot")) or pd.isna(r.get("atm_iv")):
        return dict(ts=str(ts), book=book, symbol=symbol, action="skip", note="no spot/IV")
    if book == "index":
        expiry = _next_tuesday(src.expiries(symbol), ts, C.MIN_DTE)
    else:
        expiry = _next_monthly(src.expiries(symbol), ts)
        if expiry and ev.blocked(events, symbol, ts, expiry):
            return dict(ts=str(ts), book=book, symbol=symbol, action="skip", note="event in option life")
    if not expiry:
        return dict(ts=str(ts), book=book, symbol=symbol, action="skip", note="no expiry")
    iv = float(r["atm_iv"]) / 100.0
    t = years_to(ts, expiry)
    rv, windows, wts = var.forecast_rv_ann(var.daily_close_from_hourly(var.hourly_spot(panel)), ts)
    cmap = src.contracts(symbol, expiry)
    k = atm_forward_strike(float(r["spot"]), t, strikes=list(cmap) if cmap else None, step=src.strike_step(symbol))
    lot = src.lot_size(symbol)
    g = straddle_unit(float(r["spot"]), k, t, iv)
    prem = lot * g["price"]
    sig = var.vrp_signal(iv, rv, g["vega"], lot, prem, windows, wts)
    action = "watch"
    lots = 0
    if sig.side and cmap:
        action = f"enter_{sig.side}"
        lots = lots_for_stress(float(r["spot"]), k, expiry, ts, iv, lot, hedge=True, side=sig.side)
    elif sig.side is None:
        action = "skip"
    elif not cmap:
        action, sig.reason = "skip", "no option tape"
    return dict(
        ts=str(ts),
        book=book,
        symbol=symbol,
        action=action,
        expiry=expiry or "",
        K=k,
        lots=lots,
        side=sig.side or "",
        vrp_pts=sig.vrp_pts,
        rv_forecast=sig.rv_forecast,
        rv_windows=",".join(str(x) for x in windows),
        hedge_frequency=C.HEDGE_FREQUENCY,
        hedge_underlying=C.HEDGE_UNDERLYING if book == "index" else f"{symbol}_spot_proxy",
        note=sig.reason,
    )


def write_paper_blotter(src, path: Path | None = None) -> Path:
    nifty = src.panel(C.INDEX)
    ts = pd.Timestamp(pd.to_datetime(nifty["timestamp"]).max())
    events = ev.load_events()
    membership = uni.load_membership()
    rows = [_row_for(src, ts, C.INDEX, "index", events, membership)]
    for sym in uni.constituents_asof(ts, membership=membership):
        rows.append(_row_for(src, ts, sym, "stock", events, membership))
    df = pd.DataFrame(rows)
    out = path or (C.CACHE_DIR / "paper_blotter.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    if path is None:
        C.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(C.OUTPUT_DIR / "paper_blotter.csv", index=False)
    return out
