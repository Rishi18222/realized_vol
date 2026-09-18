"""Stress scenarios: jump, IV crush, missing tape, event-in-life. Synthetic tape only."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from . import calendar_events as ev
from . import config as C
from .engine import Engine
from .synthetic import SyntheticSource
from .variance import budget_exhausted, crush_take, sold_variance


def _jump_source() -> SyntheticSource:
    src = SyntheticSource(seed=11)
    panel = src._panels["NIFTY"].copy()
    i = len(panel) // 2
    panel.loc[panel.index[i], "spot"] = float(panel.loc[panel.index[i], "spot"]) * 1.06
    src._panels["NIFTY"] = panel
    return src


def _crush_iv(src: SyntheticSource) -> None:
    panel = src._panels["NIFTY"].copy()
    mid = len(panel) // 2
    panel.loc[panel.index[mid] :, "atm_iv"] = panel.loc[panel.index[mid] :, "atm_iv"] * 0.35
    src._panels["NIFTY"] = panel


def run_stress(out_dir: Path | None = None) -> pd.DataFrame:
    d = Path(out_dir or (C.CACHE_DIR / "stress"))
    d.mkdir(parents=True, exist_ok=True)
    rows = []

    src = _jump_source()
    res = Engine(src, C.BACKTESTS["D"]).run()
    reasons = set(res.trades["exit_reason"].tolist()) if not res.trades.empty else set()
    hit = bool(reasons & {"variance_budget", "running_hot", "em_stress"})
    rows.append(dict(name="spot_jump_6pct", pass_=hit, detail=",".join(sorted(reasons)) or "no trades"))
    res.trades.to_csv(d / "jump_trades.csv", index=False)

    src2 = SyntheticSource(seed=3)
    _crush_iv(src2)
    sold = sold_variance(0.16, 8 / 365.25)
    crush_ok = crush_take(0.16 * 0.35, 6 / 365.25, sold, 0.01 * sold)
    rows.append(dict(name="iv_crush_rule", pass_=crush_ok, detail=f"crush_take={crush_ok}"))

    src3 = SyntheticSource(seed=7)
    src3._ohlc = {k: v.iloc[0:0] for k, v in src3._ohlc.items()}
    res3 = Engine(src3, C.BACKTESTS["A"]).run()
    skip_tape = bool(len(res3.skips) and res3.trades.empty)
    rows.append(
        dict(
            name="missing_option_tape",
            pass_=skip_tape,
            detail=f"trades={len(res3.trades)} skips={len(res3.skips)}",
        )
    )

    events_before = pd.DataFrame([{"symbol": "INFY", "date": "2026-03-16", "event_type": "earnings"}])
    events_during = pd.DataFrame([{"symbol": "INFY", "date": "2026-04-10", "event_type": "earnings"}])
    events_after = pd.DataFrame([{"symbol": "INFY", "date": "2026-04-17", "event_type": "earnings"}])
    for df in (events_before, events_during, events_after):
        df["date"] = pd.to_datetime(df["date"])
    entry, expiry = "2026-03-17", "2026-04-16"
    before = ev.blocked(events_before, "INFY", entry, expiry)
    during = ev.blocked(events_during, "INFY", entry, expiry)
    after = ev.blocked(events_after, "INFY", entry, expiry)
    rows.append(
        dict(
            name="event_in_life_not_tminus2",
            pass_=(not before) and during and (not after),
            detail=f"day-before={before} in-life={during} after-expiry={after}",
        )
    )

    rows.append(
        dict(
            name="budget_is_full_sold_var",
            pass_=budget_exhausted(1.0, 1.0) and not budget_exhausted(0.80, 1.0),
            detail="80% of sold_var does not exit; 100% does",
        )
    )

    df = pd.DataFrame(rows)
    df.to_csv(d / "stress_summary.csv", index=False)
    print(df.to_string(index=False))
    return df
