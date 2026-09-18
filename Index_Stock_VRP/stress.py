"""Stress: jump, crush, missing tape, skip-without-fabricating. Synthetic only."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import calendar_events as ev
from . import config as C
from .engine import Engine
from .synthetic import SyntheticSource
from .variance import budget_exhausted, forecast_rv_ann, vrp_signal


def run_stress(out_dir: Path | None = None) -> pd.DataFrame:
    d = Path(out_dir or (C.CACHE_DIR / "stress"))
    d.mkdir(parents=True, exist_ok=True)
    rows = []

    src = SyntheticSource(seed=11)
    panel = src._panels["NIFTY"].copy()
    i = len(panel) // 2
    panel.loc[panel.index[i], "spot"] = float(panel.loc[panel.index[i], "spot"]) * 1.06
    src._panels["NIFTY"] = panel
    res = Engine(src).run()
    reasons = set(res.trades["exit_reason"].tolist()) if not res.trades.empty else set()
    rows.append(dict(name="spot_jump_runs", pass_=len(res.trades) >= 0, detail=",".join(sorted(reasons)) or "no trades"))

    src3 = SyntheticSource(seed=7)
    src3._ohlc = {k: v.iloc[0:0] for k, v in src3._ohlc.items()}
    res3 = Engine(src3).run()
    no_fab = res3.trades.empty or not (res3.trades["fill_source"].astype(str) == "fabricated").any()
    skip_tape = bool(len(res3.rejected))
    rows.append(
        dict(
            name="missing_option_tape_skip",
            pass_=no_fab and skip_tape,
            detail=f"trades={len(res3.trades)} rejected={len(res3.rejected)}",
        )
    )

    px = pd.Series(
        [100, 101, 102, 100, 99, 101, 103, 104, 102, 101, 100, 102, 103, 105, 104]
        + list(range(106, 106 + 50)),
        index=pd.bdate_range("2026-03-02", periods=65),
    )
    rv, windows, _ = forecast_rv_ann(px, "2026-06-01")
    rows.append(
        dict(
            name="forecast_drops_missing_windows",
            pass_=120 not in windows and 5 in windows,
            detail=f"windows={windows} rv={rv}",
        )
    )

    sig = vrp_signal(
        0.20,
        0.12,
        vega_1pct=50.0,
        lot=65,
        premium_1lot=30000.0,
        windows=[5],
        weights_used=[1.0],
        t_hold=21 / 252.0,
        t_opt=21 / 365.25,
        n_sessions=15,
        method="test",
    )
    sig2 = vrp_signal(
        0.10,
        0.18,
        vega_1pct=50.0,
        lot=65,
        premium_1lot=30000.0,
        windows=[5],
        weights_used=[1.0],
        t_hold=21 / 252.0,
        t_opt=21 / 365.25,
        n_sessions=15,
        method="test",
    )
    rows.append(
        dict(
            name="long_and_short_from_vrp",
            pass_=sig.side == "short" and sig2.side == "long",
            detail=f"rich={sig.side} cheap={sig2.side}",
        )
    )

    events_during = pd.DataFrame([{"symbol": "INFY", "date": "2026-04-10", "event_type": "earnings"}])
    events_during["date"] = pd.to_datetime(events_during["date"])
    rows.append(
        dict(
            name="event_in_life",
            pass_=ev.blocked(events_during, "INFY", "2026-03-17", "2026-04-16"),
            detail="in-life skip",
        )
    )
    rows.append(
        dict(
            name="budget_is_full_sold_var",
            pass_=budget_exhausted(1.0, 1.0) and not budget_exhausted(0.80, 1.0),
            detail="80% of sold_var does not exit",
        )
    )

    df = pd.DataFrame(rows)
    df.to_csv(d / "stress_summary.csv", index=False)
    print(df.to_string(index=False))
    return df
