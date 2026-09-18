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


def _row_for(src, ts, symbol, book, events, membership, *, capital: float, sessions) -> dict:
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
    t_opt = years_to(ts, expiry)
    horizon = var.trade_horizon(ts, book, expiry)
    n_sess, sess_src = var.trading_sessions_to_horizon(sessions, ts, horizon)
    t_hold = var.remaining_t_years(n_sess)
    daily = var.daily_close_from_hourly(var.hourly_spot(panel))
    rv, windows, wts, method = var.tenor_forecast_rv(daily, ts, n_sess)
    method = f"{method}|{sess_src}"
    cmap = src.contracts(symbol, expiry)
    k = atm_forward_strike(float(r["spot"]), t_opt, strikes=list(cmap) if cmap else None, step=src.strike_step(symbol))
    lot = src.lot_size(symbol)
    g = straddle_unit(float(r["spot"]), k, t_opt, iv)
    prem = lot * g["price"]
    sig = var.vrp_signal(
        iv,
        rv,
        g["vega"],
        lot,
        prem,
        windows,
        wts,
        t_hold=t_hold,
        t_opt=t_opt,
        n_sessions=n_sess,
        method=method,
    )
    action = "watch"
    lots = 0
    if sig.side and cmap:
        action = f"enter_{sig.side}"
        lots = lots_for_stress(
            float(r["spot"]), k, expiry, ts, iv, lot, hedge=True, side=sig.side, capital=capital
        )
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
        n_sessions=n_sess,
        t_hold=t_hold,
        implied_remaining_var=sig.implied_remaining_var,
        expected_remaining_var=sig.expected_remaining_var,
        net_edge=sig.net_1lot,
        rv_method=method,
        hedge_frequency=C.HEDGE_FREQUENCY,
        hedge_underlying=C.HEDGE_UNDERLYING if book == "index" else f"{symbol}_spot_proxy",
        note=sig.reason,
    )


def write_paper_blotter(src, path: Path | None = None) -> Path:
    nifty = src.panel(C.INDEX)
    ts = pd.Timestamp(pd.to_datetime(nifty["timestamp"]).max())
    events = ev.load_events()
    membership = uni.load_membership()
    names = [s for s in uni.constituents_asof(ts, membership=membership) if s != C.INDEX]
    per = C.TARGET_CAPITAL / max(len(names), 1)
    sessions = var.session_days_from_panel(nifty)
    rows = [_row_for(src, ts, C.INDEX, "index", events, membership, capital=C.TARGET_CAPITAL, sessions=sessions)]
    for sym in names:
        rows.append(_row_for(src, ts, sym, "stock", events, membership, capital=per, sessions=sessions))
    df = pd.DataFrame(rows)
    out = path or (C.CACHE_DIR / "paper_blotter.csv")
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    if path is None:
        C.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        df.to_csv(C.OUTPUT_DIR / "paper_blotter.csv", index=False)
    return out
