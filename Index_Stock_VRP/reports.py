"""One output set: trade_log, hourly_risk, hedge_log, rejected_signals, daily_performance."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config as C
from . import schemas
from .engine import EngineResult


def write_result(res: EngineResult, out_dir: Path | None = None) -> Path:
    d = Path(out_dir or C.CACHE_DIR)
    d.mkdir(parents=True, exist_ok=True)
    charts = d / "charts"
    charts.mkdir(parents=True, exist_ok=True)
    schemas.conform(res.trades, schemas.TRADE_LOG).to_csv(d / "trade_log.csv", index=False)
    schemas.conform(res.hourly, schemas.HOURLY_RISK).to_csv(d / "hourly_risk.csv", index=False)
    schemas.conform(res.hedges, schemas.HEDGE_LOG).to_csv(d / "hedge_log.csv", index=False)
    schemas.conform(res.rejected, schemas.REJECTED).to_csv(d / "rejected_signals.csv", index=False)
    schemas.conform(res.daily, schemas.DAILY).to_csv(d / "daily_performance.csv", index=False)
    _equity_chart(res, charts / "equity.png")
    _book_chart(res, charts / "book_pnl.png")
    _vrp_chart(res, charts / "vrp_pnl.png")
    return d


def _equity_chart(res: EngineResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    ax, ax2 = axes
    if res.trades.empty:
        ax.set_title("no trades")
    else:
        t = res.trades.copy()
        t["exit_ts"] = pd.to_datetime(t["exit_ts"])
        t = t.sort_values("exit_ts")
        t["cum"] = t["pnl"].cumsum()
        ax.plot(t["exit_ts"], t["cum"], color="#1f4e79", lw=1.8, label="total")
        for book, col in (("index", "#c45"), ("stock", "#2a7")):
            b = t[t["book"] == book]
            if not b.empty:
                ax.plot(b["exit_ts"], b["pnl"].cumsum(), lw=1.2, color=col, label=book)
        ax.legend()
        ax.set_title(f"Two-book VRP  hedge={C.HEDGE_FREQUENCY}  {C.HEDGE_UNDERLYING}")
        ax.set_ylabel("Cumulative P&L (₹)")
        dd = t["cum"] - t["cum"].cummax()
        ax2.fill_between(t["exit_ts"], dd, 0, color="#a33", alpha=0.35)
        ax2.set_ylabel("Drawdown")
    ax.grid(True, alpha=0.3)
    ax2.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _book_chart(res: EngineResult, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    if res.trades.empty:
        ax.set_title("no book P&L")
    else:
        g = res.trades.groupby("book")["pnl"].sum()
        colors = ["#1f4e79" if v >= 0 else "#a33" for v in g.values]
        ax.bar(g.index.astype(str), g.values, color=colors)
        ax.set_ylabel("Total P&L (₹)")
        ax.set_title("Index vs stock VRP books")
        ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _vrp_chart(res: EngineResult, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    if res.trades.empty or "vrp_pts" not in res.trades.columns:
        ax.set_title("no VRP scatter")
    else:
        t = res.trades.dropna(subset=["vrp_pts", "pnl"])
        c = np.where(t["side"] == "short", "#c45", "#2a7")
        ax.scatter(t["vrp_pts"], t["pnl"], c=c, alpha=0.75)
        ax.axhline(0, color="#666", lw=0.8)
        ax.axvline(0, color="#666", lw=0.8)
        ax.set_xlabel("Entry VRP (IV − forecast RV, vol pts)")
        ax.set_ylabel("Trade P&L (₹)")
        ax.set_title("VRP vs P&L  (red=short, green=long)")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def write_summary(res: EngineResult, path: Path | None = None) -> pd.DataFrame:
    rows = []
    t = res.trades
    if t is None or t.empty:
        df = pd.DataFrame([dict(book="all", n=0, hit=np.nan, pnl=0.0)])
    else:
        for book, g in t.groupby("book"):
            rows.append(
                dict(
                    book=book,
                    n=len(g),
                    n_short=int((g["side"] == "short").sum()),
                    n_long=int((g["side"] == "long").sum()),
                    hit=float((g["pnl"] > 0).mean()),
                    pnl=float(g["pnl"].sum()),
                    mean=float(g["pnl"].mean()),
                    costs=float(g["costs"].sum()),
                    pnl_opt=float(g["pnl_opt"].sum()),
                    pnl_hedge=float(g["pnl_hedge"].sum()),
                )
            )
        rows.append(
            dict(
                book="all",
                n=len(t),
                n_short=int((t["side"] == "short").sum()),
                n_long=int((t["side"] == "long").sum()),
                hit=float((t["pnl"] > 0).mean()),
                pnl=float(t["pnl"].sum()),
                mean=float(t["pnl"].mean()),
                costs=float(t["costs"].sum()),
                pnl_opt=float(t["pnl_opt"].sum()),
                pnl_hedge=float(t["pnl_hedge"].sum()),
            )
        )
        df = pd.DataFrame(rows)
    out = path or (C.CACHE_DIR / "summary.csv")
    df.to_csv(out, index=False)
    return df
