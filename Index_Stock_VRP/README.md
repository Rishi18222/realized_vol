# Index VRP and Stock VRP (framework v3)

One backtest, **two independent books**. No A–H ladder. No always-in book.

Spec/plan files under `/opt/cursor/agent-store/...` were not on this worker.

## Books

1. **Index** — Daily scan. If Nifty is flat, implied forward variance vs 5/20/60/120 forecast RV decides **short or long** the next-Tuesday ATM-forward weekly straddle (min 8 DTE). Delta-hedge with the Nifty **spot-as-futures proxy**. Independent of stocks.
2. **Stocks** — Daily scan of **every PIT Nifty 50 name**. Same signal on that name’s own IV/RV. Monthly ATM-forward straddle, hedged with **that stock’s spot proxy, never Nifty**. No option tape → `rejected_signals` skip, nothing fabricated.

If flat and no signal: do nothing until the next session. If in a trade: 1h hedge + exit rules until flat, then resume the scan.

## Signal

Forecast RV is a HAR mix of 5 / 20 / 60 / 120 **day** realized variance (weights 0.4 / 0.3 / 0.2 / 0.1). Missing windows (typical for 60d and 120d on a ~180d Groww tape) are **dropped and weights renormalized**. VRP = IV² − RV_forecast². After round-trip statutory costs at mid, 2× slippage, and a cost buffer: positive net edge → **short** straddle; negative → **long**. Tiny gaps below `min_vrp_pts` stay flat.

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
