"""IS / validation / OOS. Groww ~180d is too short; say so instead of splitting."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config as C


def evaluate(n_index_trades: int, n_stock_trades: int, n_sessions: int) -> dict:
    # Need many independent weekly observations per fold. 180d ≈ 25 Mondays.
    enough = n_sessions >= 500 and n_index_trades >= 150
    if enough:
        return {
            "ok": True,
            "reason": "history long enough for a chronological 60/20/20 split",
            "n_sessions": n_sessions,
            "n_index_trades": n_index_trades,
            "n_stock_trades": n_stock_trades,
            "is_frac": 0.60,
            "val_frac": 0.20,
            "oos_frac": 0.20,
        }
    return {
        "ok": False,
        "reason": (
            "Groww 1h history is capped near 180 calendar days. "
            f"NIFTY sessions={n_sessions}, index trades={n_index_trades}, stock trades={n_stock_trades}. "
            "Too short for in-sample / validation / out-of-sample; numbers are one sample, not a split."
        ),
        "n_sessions": n_sessions,
        "n_index_trades": n_index_trades,
        "n_stock_trades": n_stock_trades,
        "is_frac": None,
        "val_frac": None,
        "oos_frac": None,
    }


def write_disclaimer(results: dict, inventory: dict | None = None, path: Path | None = None) -> Path:
    n_idx = 0
    n_stk = 0
    for res in results.values():
        t = res.trades
        if t is None or t.empty:
            continue
        n_idx += int((t["book"] == "index").sum()) if "book" in t.columns else 0
        n_stk += int((t["book"] == "stock").sum()) if "book" in t.columns else 0
    n_sess = 0
    if inventory and "split" in inventory:
        n_sess = int(inventory["split"].get("n_nifty_sessions") or 0)
    report = evaluate(n_idx, n_stk, n_sess)
    out = Path(path or (C.CACHE_DIR / "split_disclaimer.md"))
    lines = [
        "# In-sample / validation / out-of-sample",
        "",
        report["reason"],
        "",
        f"- n_sessions: {report['n_sessions']}",
        f"- n_index_trades (A–H, overlapping books): {report['n_index_trades']}",
        f"- n_stock_trades: {report['n_stock_trades']}",
        f"- split applied: {'yes' if report['ok'] else 'no'}",
        "",
    ]
    out.write_text("\n".join(lines))
    return out
