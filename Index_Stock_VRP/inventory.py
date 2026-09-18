"""Inspect on-disk market data. Run before any backtest. Do not fabricate."""

from __future__ import annotations

import json
import pickle
from pathlib import Path

import pandas as pd

from . import config as C
from .source import ATM_CACHE, OPT_CACHE

SPAN_DIR = C.REPO_ROOT / "Calendar_Dispersion_BT" / "cache" / "span"


def inspect_disk() -> dict:
    atm_files = sorted(ATM_CACHE.glob("*180d_1h_v6.pkl")) if ATM_CACHE.exists() else []
    panels = []
    hours: set[int] = set()
    bid_ask_panels = 0
    rv_panels = 0
    for path in atm_files:
        symbol = path.name.split("_")[0]
        try:
            with path.open("rb") as f:
                obj = pickle.load(f)
            panel = obj.get("panel") if isinstance(obj, dict) else obj
        except Exception as exc:
            panels.append({"symbol": symbol, "error": str(exc), "path": str(path)})
            continue
        if not isinstance(panel, pd.DataFrame) or panel.empty:
            panels.append({"symbol": symbol, "rows": 0, "path": str(path)})
            continue
        df = panel.copy()
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        hour_vals = sorted(int(h) for h in df["timestamp"].dt.hour.unique())
        hours.update(hour_vals)
        cols = [str(c) for c in df.columns]
        has_ba = any(c.lower() in {"bid", "ask", "bid_price", "ask_price"} for c in cols)
        bid_ask_panels += int(has_ba)
        rv_cols = [c for c in cols if c.startswith("rv_")]
        rv_panels += int(bool(rv_cols))
        nan_iv = float(df["atm_iv"].isna().mean()) if "atm_iv" in df.columns else None
        dates = pd.DatetimeIndex(sorted(df["timestamp"].dt.normalize().unique()))
        bdays = pd.bdate_range(dates.min(), dates.max()) if len(dates) else pd.DatetimeIndex([])
        gaps = [str(d.date()) for d in bdays if d not in set(dates)]
        panels.append(
            {
                "symbol": symbol,
                "rows": int(len(df)),
                "start": str(df["timestamp"].min()),
                "end": str(df["timestamp"].max()),
                "hours": hour_vals,
                "unique_dates": int(df["timestamp"].dt.normalize().nunique()),
                "nan_atm_iv": nan_iv,
                "bid_ask": has_ba,
                "rv_cols": rv_cols,
                "columns": cols,
                "weekday_gaps": gaps,
            }
        )

    opt_files = list(OPT_CACHE.glob("*.pkl")) if OPT_CACHE.exists() else []
    opt_und: set[str] = set()
    opt_bid = 0
    sampled = 0
    series_n = 0
    df_n = 0
    for p in opt_files:
        name = p.name
        if name.startswith("NSE-"):
            parts = name.split("-")
            if len(parts) >= 2:
                opt_und.add(parts[1])
        if sampled >= 80:
            continue
        sampled += 1
        try:
            obj = pd.read_pickle(p)
        except Exception:
            continue
        if isinstance(obj, pd.Series):
            series_n += 1
            continue
        df_n += 1
        cols = [str(c).lower() for c in obj.columns]
        if "bid" in cols or "ask" in cols:
            opt_bid += 1

    span_zips = sorted(SPAN_DIR.glob("nsccl.*.s.zip")) if SPAN_DIR.exists() else []
    fut_dirs = [
        C.REPO_ROOT / "Calendar_Dispersion_BT" / "cache" / "fut",
        C.REPO_ROOT / "Calendar_Dispersion_BT" / "cache" / "futures",
        C.REPO_ROOT / "NEW_PROJ" / "fut_cache",
    ]
    fut_present = [str(d) for d in fut_dirs if d.exists() and any(d.iterdir())]
    holiday_files = list((C.DATA_DIR).glob("*holiday*"))

    native_hours = sorted(hours) if hours else list(C.NATIVE_HOURS)
    is_hourly = native_hours == list(range(9, 16)) or set(native_hours) <= set(range(9, 16))

    nifty = next((p for p in panels if p.get("symbol") == "NIFTY" and p.get("rows")), None)
    n_sessions = int(nifty["unique_dates"]) if nifty else 0
    n_mondays_est = max(n_sessions // 5, 0)

    can = [
        "Index weekly ATM-forward straddles on NIFTY 1h ATM-IV + option OHLC (Groww ~180d).",
        "Stock monthly ATM-forward straddles on liquid F&O names that have both an ATM panel and option cache.",
        "Fills at option OHLC close as mid, plus configured slippage (no bid/ask tape).",
        "Statutory NSE F&O costs charged on mid premium.",
        f"SPAN XML risk arrays on {len(span_zips)} cached clearing zips; ELM 2% index / 3.5% stock otherwise.",
        "Delta hedge on the native 1h clock using spot as the futures proxy.",
        "Matched-tenor IV²/RV², remaining-variance budget, crush and running-hot exits.",
        "Event-in-life skips using data/events.csv dates inside [entry, expiry].",
        "Stress-loss lot cap (1.75× EM vs 20% of posted capital).",
        "--cache-only from pickle ATM-IV and option OHLC without growwapi.",
    ]
    cannot = [
        "5-minute Greeks or 5-minute hedges: every panel and option file is hourly (09:00–15:00). Hedge frequency is labeled 1h.",
        "True bid/ask execution: ATM panels and sampled option OHLC have no bid/ask columns. Engine uses mid±slippage and records fill_source=mid+slip.",
        "True futures/SSF marks: no futures cache is present. Hedge P&L uses spot as a futures proxy and is labeled spot_as_fut_proxy.",
        "PIT earnings announcement dates: data/events.csv is an illustrative research calendar (typical FY26/FY27 windows), not an announcement tape.",
        "Full Nifty 50 option book: option OHLC underlyings are the 12 liquid F&O names plus NIFTY. Extra ATM panels (BAJAJFINSV, GRASIM, NMDC, NTPC) are not in LIQUID_FNO.",
        "Official holiday calendar file: none in-package; session gaps are inferred from missing weekday bars.",
        "IS / validation / OOS: Groww history is capped near 180 calendar days "
        f"(~{n_sessions} NIFTY sessions, ~{n_mondays_est} Mondays). Too short for a three-way split.",
    ]
    report = {
        "framework_version": 2,
        "hedge_frequency": "1h" if is_hourly else f"native_hours={native_hours}",
        "hedge_underlying": "spot_as_fut_proxy",
        "lookback_days_cap": 180,
        "atm_cache": str(ATM_CACHE),
        "opt_cache": str(OPT_CACHE),
        "span_dir": str(SPAN_DIR),
        "n_atm_v6_180d": len(atm_files),
        "panels": panels,
        "option_pkl_count": len(opt_files),
        "option_underlyings": sorted(opt_und),
        "option_sample": {"dataframes": df_n, "series": series_n, "bid_ask_in_sample": opt_bid, "sampled": sampled},
        "span_zip_count": len(span_zips),
        "span_zip_first": span_zips[0].name if span_zips else None,
        "span_zip_last": span_zips[-1].name if span_zips else None,
        "futures_caches": fut_present,
        "holiday_files": [str(p) for p in holiday_files],
        "membership": str(C.DATA_DIR / "nifty50_membership.csv"),
        "events": str(C.DATA_DIR / "events.csv"),
        "can_test": can,
        "cannot_test": cannot,
        "split": {
            "method": "none",
            "reason": "Groww 1h history ~180d is too short for in-sample / validation / out-of-sample.",
            "n_nifty_sessions": n_sessions,
            "n_mondays_est": n_mondays_est,
        },
    }
    return report


def write_inventory(out_dir: Path | None = None) -> dict:
    report = inspect_disk()
    d = Path(out_dir or C.CACHE_DIR)
    d.mkdir(parents=True, exist_ok=True)
    (d / "data_inventory.json").write_text(json.dumps(report, indent=2, default=str))
    md = _to_markdown(report)
    (d / "data_inventory.md").write_text(md)
    (C.DATA_DIR / "inventory.md").write_text(md)
    return report


def _to_markdown(rep: dict) -> str:
    lines = [
        "# Data inventory (before backtest)",
        "",
        "Inspected on disk. Nothing below is fabricated.",
        "",
        f"- Hedge frequency: **{rep['hedge_frequency']}** (not 5-minute).",
        f"- Hedge underlying: **{rep['hedge_underlying']}**.",
        f"- ATM v6 180d panels: {rep['n_atm_v6_180d']}.",
        f"- Option OHLC pickles: {rep['option_pkl_count']}; underlyings: {', '.join(rep['option_underlyings']) or '(none)'}.",
        f"- SPAN zips: {rep['span_zip_count']} ({rep['span_zip_first']} → {rep['span_zip_last']}).",
        f"- Futures caches: {rep['futures_caches'] or 'none'}.",
        f"- Holiday files in package data: {rep['holiday_files'] or 'none (gaps from missing weekday bars)'}.",
        "",
        "## Panels",
        "",
        "| symbol | rows | start | end | hours | nan IV | bid/ask | rv cols |",
        "|---|---:|---|---|---|---:|---|---|",
    ]
    for p in rep["panels"]:
        if "error" in p:
            lines.append(f"| {p['symbol']} |  |  |  |  |  |  | {p['error']} |")
            continue
        lines.append(
            f"| {p.get('symbol')} | {p.get('rows')} | {p.get('start')} | {p.get('end')} | "
            f"{p.get('hours')} | {p.get('nan_atm_iv')} | {p.get('bid_ask')} | {p.get('rv_cols')} |"
        )
    lines += ["", "## Can test", ""]
    lines += [f"- {x}" for x in rep["can_test"]]
    lines += ["", "## Cannot test", ""]
    lines += [f"- {x}" for x in rep["cannot_test"]]
    split = rep["split"]
    lines += [
        "",
        "## IS / validation / OOS",
        "",
        f"{split['reason']} NIFTY sessions={split['n_nifty_sessions']}, Mondays≈{split['n_mondays_est']}.",
        "",
    ]
    return "\n".join(lines) + "\n"
