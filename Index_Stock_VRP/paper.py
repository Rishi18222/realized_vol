"""Paper blotter from the last available bar. Same rules as backtests D and H."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config as C
from . import calendar_events as ev
from . import universe as uni
from . import variance as var
from .engine import _next_monthly, _next_tuesday
from .pricing import atm_forward_strike, years_to
from .sizing import lots_for_stress
from .source import daily_close, row_at


def write_paper_blotter(src, path: Path | None = None) -> Path:
    nifty = src.panel(C.INDEX)
    ts = pd.Timestamp(pd.to_datetime(nifty["timestamp"]).max())
    events = ev.load_events()
    membership = uni.load_membership()
    rows = []
    row = row_at(nifty, ts)
    if row is not None and pd.notna(row.get("spot")):
        expiry = _next_tuesday(src.expiries(C.INDEX), ts, C.MIN_DTE)
        iv = float(row["atm_iv"]) / 100.0 if pd.notna(row.get("atm_iv")) else float("nan")
        rv = var.rv_nd_pct(daily_close(nifty), ts)
        vrp = var.vrp_pts(float(row["atm_iv"]), rv) if pd.notna(row.get("atm_iv")) else float("nan")
        ok, why, _ = var.signal_ok(float(row["atm_iv"]), rv) if pd.notna(row.get("atm_iv")) else (False, "no IV", float("nan"))
        monday = int(ts.weekday()) == C.ROLL_WEEKDAY
        action = "enter_short" if monday and expiry and ok else "watch"
        note = why if expiry else "no Tuesday ≥8 DTE"
        if expiry and monday and not ok:
            action = "skip"
        lots = 0
        k = float("nan")
        if expiry and pd.notna(row.get("spot")) and iv == iv:
            t = years_to(ts, expiry)
            cmap = src.contracts(C.INDEX, expiry)
            k = atm_forward_strike(float(row["spot"]), t, strikes=list(cmap) if cmap else None)
            lots = lots_for_stress(
                float(row["spot"]), k, expiry, ts, iv, src.lot_size(C.INDEX), hedge=True
            )
        rows.append(
            dict(
                ts=str(ts),
                book="index",
                backtest="D",
                symbol=C.INDEX,
                action=action,
                expiry=expiry or "",
                K=k,
                lots=lots,
                vrp=vrp,
                note=note,
                monday_entry=monday,
            )
        )
    for sym in uni.tradeable_asof(ts, membership=membership):
        try:
            panel = src.panel(sym)
        except Exception as exc:
            rows.append(dict(ts=str(ts), book="stock", backtest="H", symbol=sym, action="skip", note=str(exc)))
            continue
        r = row_at(panel, ts)
        if r is None or pd.isna(r.get("spot")) or pd.isna(r.get("atm_iv")):
            rows.append(dict(ts=str(ts), book="stock", backtest="H", symbol=sym, action="skip", note="no spot/IV"))
            continue
        expiry = _next_monthly(src.expiries(sym), ts)
        blocked = bool(expiry) and ev.blocked(events, sym, ts, expiry)
        rv = var.rv_nd_pct(daily_close(panel), ts)
        ok, why, gap = var.signal_ok(float(r["atm_iv"]), rv)
        action = "watch"
        note = why
        lots = 0
        k = float("nan")
        if expiry and not blocked and ok and int(ts.weekday()) == C.ROLL_WEEKDAY:
            action = "enter_short"
            t = years_to(ts, expiry)
            cmap = src.contracts(sym, expiry)
            k = atm_forward_strike(float(r["spot"]), t, strikes=list(cmap) if cmap else None, step=src.strike_step(sym))
            lots = lots_for_stress(
                float(r["spot"]), k, expiry, ts, float(r["atm_iv"]) / 100.0, src.lot_size(sym), hedge=True
            )
        elif blocked:
            action, note = "skip", "earnings/corporate blackout"
        elif not expiry:
            action, note = "skip", "no monthly DTE window"
        elif not ok:
            action, note = "skip", why
        rows.append(
            dict(
                ts=str(ts),
                book="stock",
                backtest="H",
                symbol=sym,
                action=action,
                expiry=expiry or "",
                K=k,
                lots=lots,
                vrp=gap,
                note=note,
                monday_entry=int(ts.weekday()) == C.ROLL_WEEKDAY,
            )
        )
    df = pd.DataFrame(rows)
    out = path or (C.CACHE_DIR / "paper_blotter.csv")
    df.to_csv(out, index=False)
    return out
