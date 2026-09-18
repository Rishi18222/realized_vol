"""Run the single two-book VRP backtest (daily scan, long or short vol)."""

from __future__ import annotations

import argparse
from pathlib import Path

from . import config as C
from .engine import Engine
from .inventory import write_inventory
from .paper import write_paper_blotter
from .reports import write_result, write_summary
from .splits import write_disclaimer


def _source(*, synthetic: bool, lookback: int, refetch: bool, cache_only: bool):
    if synthetic:
        from .synthetic import SyntheticSource

        return SyntheticSource()
    from .source import GrowwSource

    return GrowwSource(lookback_days=lookback, refetch=refetch, cache_only=cache_only)


def run_backtest(
    *,
    synthetic: bool = False,
    lookback: int = C.LOOKBACK_DAYS,
    refetch: bool = False,
    cache_only: bool = False,
):
    inv = None
    if not synthetic:
        inv = write_inventory()
        print("=== data inventory (before backtest) ===")
        print((C.CACHE_DIR / "data_inventory.md").read_text()[:2500])
        print(f"cannot_test ({len(inv['cannot_test'])} items)")
        n_sess = int(inv.get("split", {}).get("n_nifty_sessions") or 0)
        print(
            f"No OOS split: Groww ~180d, NIFTY sessions={n_sess}. "
            "Results are one sample, not in-sample/validation/out-of-sample."
        )
    else:
        print("=== synthetic tape — live inventory skipped ===")

    src = _source(synthetic=synthetic, lookback=lookback, refetch=refetch, cache_only=cache_only)
    eng = Engine(src)
    res = eng.run()
    write_result(res)
    write_result(res, C.OUTPUT_DIR)
    write_disclaimer(res, inventory=inv)
    summary = write_summary(res)
    write_summary(res, C.OUTPUT_DIR / "summary.csv")
    print("\n=== summary ===")
    print(summary.to_string(index=False))
    if res.trades.empty:
        print(f"  no trades  rejected={len(res.rejected)}")
    else:
        t = res.trades
        print(
            f"  trades {len(t)}  long {(t['side']=='long').sum()}  short {(t['side']=='short').sum()}  "
            f"hit {(t['pnl']>0).mean():.1%}  pnl {t['pnl'].sum():,.0f}  "
            f"hedge={C.HEDGE_FREQUENCY}"
        )
    return res


def main() -> None:
    p = argparse.ArgumentParser(description="Two independent VRP books: index weekly + stock monthly")
    p.add_argument("--lookback", type=int, default=C.LOOKBACK_DAYS)
    p.add_argument("--config", type=str, default="", help="YAML or JSON config path")
    p.add_argument("--synthetic", action="store_true")
    p.add_argument("--cache-only", action="store_true", help="disk caches only; growwapi not required")
    p.add_argument("--refetch", action="store_true")
    p.add_argument("--paper", action="store_true")
    args = p.parse_args()
    if args.config:
        C.load_file(Path(args.config))
    run_backtest(
        synthetic=args.synthetic,
        lookback=min(args.lookback, 180),
        refetch=args.refetch,
        cache_only=args.cache_only,
    )
    if args.paper:
        src = _source(
            synthetic=args.synthetic,
            lookback=min(args.lookback, 180),
            refetch=args.refetch,
            cache_only=args.cache_only,
        )
        path = write_paper_blotter(src)
        print(f"paper blotter {path}")


if __name__ == "__main__":
    main()
