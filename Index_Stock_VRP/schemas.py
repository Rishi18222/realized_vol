"""One output set for the two-book VRP backtest."""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADE_LOG = [
    "trade_id",
    "book",
    "symbol",
    "side",
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
    "rv_forecast",
    "vrp_var",
    "vrp_pts",
    "rv_windows",
    "sold_var",
    "path_real_var",
    "remaining_var",
    "notes",
]

HOURLY_RISK = [
    "ts",
    "book",
    "symbol",
    "side",
    "expiry",
    "K",
    "spot",
    "iv",
    "straddle_mark",
    "hedge_units",
    "hedge_frequency",
    "hedge_underlying",
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
    "span",
    "elm",
    "posted_margin",
]

HEDGE_LOG = [
    "ts",
    "book",
    "symbol",
    "side",
    "hedge_underlying",
    "hedge_frequency",
    "d_units",
    "units_after",
    "spot",
    "cost",
    "reason",
]

REJECTED = [
    "ts",
    "book",
    "symbol",
    "reason",
    "iv",
    "rv_forecast",
    "vrp_var",
    "vrp_pts",
    "net_edge",
    "rv_windows",
    "would_side",
]

DAILY = [
    "date",
    "n_index_open",
    "n_stock_open",
    "pnl_index",
    "pnl_stock",
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


def conform(df: pd.DataFrame | None, columns: list[str]) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=columns)
    out = df.copy()
    for c in columns:
        if c not in out.columns:
            out[c] = np.nan
    extra = [c for c in out.columns if c not in columns]
    return out[columns + extra]
