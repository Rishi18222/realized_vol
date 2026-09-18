"""Required CSV column order for the v2 engine."""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADES = [
    "trade_id",
    "backtest",
    "book",
    "symbol",
    "expiry",
    "K",
    "lots",
    "lot",
    "entry_ts",
    "exit_ts",
    "exit_reason",
    "dte_entry",
    "fill_source",
    "hedge_frequency",
    "hedge_underlying",
    "ce_sym",
    "pe_sym",
    "ce_open_mid",
    "pe_open_mid",
    "ce_open_fill",
    "pe_open_fill",
    "ce_close_mid",
    "pe_close_mid",
    "straddle_open",
    "straddle_close",
    "pnl_opt",
    "pnl_hedge",
    "costs",
    "pnl",
    "iv_entry",
    "rv_matched_ann",
    "var_ratio",
    "z_score",
    "sold_var",
    "path_real_var",
    "remaining_var",
    "notes",
]

HOURLY = [
    "ts",
    "backtest",
    "book",
    "symbol",
    "expiry",
    "K",
    "spot",
    "iv",
    "straddle_mark",
    "hedge_units",
    "hedge_frequency",
    "delta",
    "gamma",
    "vega",
    "theta",
    "path_real_var",
    "sold_var",
    "remaining_var",
    "running_hot_ratio",
    "pnl_opt_unreal",
    "pnl_hedge",
    "costs",
]

DAILY = [
    "date",
    "backtest",
    "book",
    "n_open",
    "pnl_opt",
    "pnl_hedge",
    "costs",
    "pnl",
    "equity",
    "drawdown",
    "span",
    "elm",
    "posted_margin",
]

RISK = [
    "ts",
    "backtest",
    "book",
    "symbol",
    "expiry",
    "lots",
    "stress_pnl_1lot",
    "stress_capital",
    "span",
    "elm",
    "posted_margin",
    "premium_mid",
    "var_ratio",
    "z_score",
    "sold_var",
    "hedge_frequency",
    "margin_source",
]

SKIPS = [
    "ts",
    "backtest",
    "book",
    "symbol",
    "reason",
    "var_ratio",
    "z_score",
]


def conform(df: pd.DataFrame | None, columns: list[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    out = df.copy()
    for c in columns:
        if c not in out.columns:
            out[c] = np.nan
    extra = [c for c in out.columns if c not in columns]
    return out[columns + extra]
