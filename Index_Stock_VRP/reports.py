"""Trade / hourly / daily / risk CSVs and charts."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config as C
from .engine import EngineResult


def write_result(spec_id: str, res: EngineResult, out_dir: Path | None = None) -> Path:
    d = Path(out_dir or (C.CACHE_DIR / spec_id))
    d.mkdir(parents=True, exist_ok=True)
    res.trades.to_csv(d / "trades.csv", index=False)
    res.hourly.to_csv(d / "hourly.csv", index=False)
    res.daily.to_csv(d / "daily.csv", index=False)
    res.risk.to_csv(d / "risk.csv", index=False)
    res.skips.to_csv(d / "skips.csv", index=False)
    _equity_chart(spec_id, res, C.CHART_DIR / f"{spec_id}_equity.png")
    _vrp_chart(spec_id, res, C.CHART_DIR / f"{spec_id}_vrp_pnl.png")
    return d


def _equity_chart(spec_id: str, res: EngineResult, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(2, 1, figsize=(11, 7), sharex=True)
    ax, ax2 = axes
    if res.trades.empty:
        ax.set_title(f"{spec_id}: no trades")
    else:
        t = res.trades.copy()
        t["exit_ts"] = pd.to_datetime(t["exit_ts"])
        t = t.sort_values("exit_ts")
        t["cum"] = t["pnl"].cumsum()
        ax.plot(t["exit_ts"], t["cum"], color="#1f4e79", lw=1.8)
        ax.fill_between(t["exit_ts"], t["cum"], 0, alpha=0.12, color="#1f4e79")
        ax.set_title(f"{spec_id}  {C.BACKTESTS[spec_id].title}")
        ax.set_ylabel("Cumulative P&L (₹)")
        dd = t["cum"] - t["cum"].cummax()
        ax2.fill_between(t["exit_ts"], dd, 0, color="#a33", alpha=0.35)
        ax2.set_ylabel("Drawdown")
    ax.grid(True, alpha=0.3)
    ax2.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def _vrp_chart(spec_id: str, res: EngineResult, path: Path) -> None:
    fig, ax = plt.subplots(figsize=(8, 5))
    if res.trades.empty or "vrp" not in res.trades.columns:
        ax.set_title(f"{spec_id}: no VRP scatter")
    else:
        t = res.trades.dropna(subset=["vrp", "pnl"])
        ax.scatter(t["vrp"], t["pnl"], c=np.where(t["pnl"] >= 0, "#2a7", "#c44"), alpha=0.75)
        ax.axhline(0, color="#666", lw=0.8)
        ax.axvline(0, color="#666", lw=0.8)
        ax.set_xlabel("Entry VRP (IV − 5d RV, vol pts)")
        ax.set_ylabel("Trade P&L (₹)")
        ax.set_title(f"{spec_id} VRP vs P&L")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)


def write_summary(results: dict[str, EngineResult], path: Path | None = None) -> pd.DataFrame:
    rows = []
    for k, res in results.items():
        t = res.trades
        spec = C.BACKTESTS[k]
        if t is None or t.empty:
            rows.append(dict(backtest=k, title=spec.title, n=0, hit=np.nan, pnl=0.0, mean=np.nan, costs=0.0))
            continue
        rows.append(
            dict(
                backtest=k,
                title=spec.title,
                n=len(t),
                hit=float((t["pnl"] > 0).mean()),
                pnl=float(t["pnl"].sum()),
                mean=float(t["pnl"].mean()),
                costs=float(t["costs"].sum()),
                pnl_opt=float(t["pnl_opt"].sum()),
                pnl_fut=float(t["pnl_fut"].sum()),
            )
        )
    df = pd.DataFrame(rows)
    out = path or (C.CACHE_DIR / "summary.csv")
    df.to_csv(out, index=False)
    fig, ax = plt.subplots(figsize=(10, 5))
    if not df.empty:
        colors = ["#1f4e79" if x >= 0 else "#a33" for x in df["pnl"]]
        ax.bar(df["backtest"], df["pnl"], color=colors)
        ax.set_ylabel("Total P&L (₹)")
        ax.set_title("Index/Stock VRP backtests A–H")
        ax.grid(True, axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(C.CHART_DIR / "AH_total_pnl.png", dpi=120)
    plt.close(fig)
    return df
