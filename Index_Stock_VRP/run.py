"""Run Index VRP / Stock VRP backtests A–H and optional paper blotter."""

from __future__ import annotations

import argparse

import pandas as pd

from . import config as C
from .engine import Engine
from .paper import write_paper_blotter
from .reports import write_result, write_summary


def _source(*, synthetic: bool, lookback: int, refetch: bool, cache_only: bool):
    if synthetic:
        from .synthetic import SyntheticSource

        return SyntheticSource()
    from .source import GrowwSource

    return GrowwSource(lookback_days=lookback, refetch=refetch, cache_only=cache_only)


def run_backtests(
    ids: list[str],
    *,
    synthetic: bool = False,
    lookback: int = C.LOOKBACK_DAYS,
    refetch: bool = False,
    cache_only: bool = False,
) -> dict:
    src = _source(synthetic=synthetic, lookback=lookback, refetch=refetch, cache_only=cache_only)
    results = {}
    for i in ids:
        spec = C.BACKTESTS[i]
        print(f"\n=== Backtest {i}: {spec.title} ===")
        eng = Engine(src, spec)
        res = eng.run()
        write_result(i, res)
        results[i] = res
        if res.trades.empty:
            print(f"  no trades  skips={len(res.skips)}")
        else:
            t = res.trades
            print(
                f"  trades {len(t)}  hit {(t['pnl']>0).mean():.1%}  "
                f"pnl {t['pnl'].sum():,.0f}  costs {t['costs'].sum():,.0f}"
            )
    summary = write_summary(results)
    print("\n=== summary ===")
    print(summary.to_string(index=False))
    return results


def main() -> None:
    p = argparse.ArgumentParser(description="Independent Index VRP and Stock VRP books")
    p.add_argument("--backtests", default="A,B,C,D,E,F,G,H", help="comma-separated A–H")
    p.add_argument("--lookback", type=int, default=C.LOOKBACK_DAYS)
    p.add_argument("--synthetic", action="store_true", help="offline GBM tape")
    p.add_argument("--cache-only", action="store_true", help="do not call Groww; use disk caches")
    p.add_argument("--refetch", action="store_true")
    p.add_argument("--paper", action="store_true", help="write a paper blotter from the last bar")
    args = p.parse_args()
    ids = [x.strip().upper() for x in args.backtests.split(",") if x.strip()]
    unknown = [i for i in ids if i not in C.BACKTESTS]
    if unknown:
        raise SystemExit(f"unknown backtests {unknown}; choose from {list(C.BACKTESTS)}")
    results = run_backtests(
        ids,
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
    return results


if __name__ == "__main__":
    main()
