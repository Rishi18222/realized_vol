# Index VRP and Stock VRP (framework v4)

One backtest, **two independent books**. No A–H ladder. No always-in book.

Spec/plan files under `/opt/cursor/agent-store/...` were not on this worker.

## Books

1. **Index** — Daily scan. If Nifty is flat, remaining-tenor VRP decides **short or long** the next-Tuesday ATM-forward weekly straddle (min 8 DTE). Horizon is the Monday roll / next Tuesday. Delta-hedge with the Nifty **spot-as-futures proxy**. Independent of stocks.
2. **Stocks** — Daily scan of **every PIT Nifty 50 name**. Same signal. Monthly ATM-forward straddle held to the configured stock exit, hedged with **that stock’s spot proxy, never Nifty**. No option tape → `rejected_signals` skip, nothing fabricated.

If flat and no signal: do nothing until the next session. If in a trade: 1h hedge + exit rules until flat, then resume the scan.

## Signal

Compared quantities, **same T**:

- `implied_remaining_var = IV² × T`
- `expected_remaining_var = forecast_RV² × T`

`T` is remaining **trading** time to the trade horizon (`n / 252`). `n` is the number of sessions from the hourly tape between the scan date and the horizon when the tape covers it; otherwise `round(5/7 × calendar DTE)` (10 calendar days → 7 trading days). Index horizon: Monday roll / next Tuesday. Stock horizon: configured stock exit DTE.

`forecast_RV` is remaining-tenor RV: lookback = `n` trading days. HAR 5/20/60/120 may **blend as a forecast of that tenor**; those windows are not the comparison tenor.

Short if implied remaining > expected remaining after statutory costs at mid, 2× slip, and the cost buffer. Long only if expected remaining realized variance exceeds remaining implied after costs. Tiny negative vol-pt gaps with a few days of T (the old 56–66 lot Nifty longs) fail this remaining-T test and are skipped until the next session.

## Labels (this tape)

- `hedge_frequency=1h` (native bars 09:00–15:00, not 5-minute)
- fills `mid+slip` (no bid/ask columns)
- index hedge `spot_as_fut_proxy`; stock hedge `{SYM}_spot_proxy`

Do **not** claim OOS. Groww history is ~180 calendar days.

## Run

```bash
python3 -m Index_Stock_VRP.run --cache-only --lookback 180 --paper
python3 -m Index_Stock_VRP.run --synthetic
python3 -m unittest Index_Stock_VRP.tests.test_vrp
```

`--cache-only` does not import `growwapi`.

## Outputs (one set, not A–H folders)

Tracked under `Index_Stock_VRP/output/` (runtime copy also under `cache/`):

- `trade_log.csv`
- `hourly_risk.csv`
- `hedge_log.csv`
- `rejected_signals.csv`
- `daily_performance.csv`
- `charts/equity.png`, `book_pnl.png`, `vrp_pnl.png`
- `data_inventory.md` (written **before** the backtest)
- `paper_blotter.csv`

JSON/YAML: `configs/default.json` and `configs/default.yaml` (same document; YAML parser falls back to JSON if PyYAML is missing).
