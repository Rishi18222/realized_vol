# Index VRP and Stock VRP (framework v2)

Independent **Index VRP** and **Stock VRP** books. No dispersion.

This replaces the v1 engine. It does **not** use IV minus 5-day RV in vol points, an 80% realized-variance exit, or T−2/T+1 earnings windows.

Spec files under `/opt/cursor/agent-store/...` were not on this worker. The 26 sections below are what this package implements.

Groww hourly ATM-IV and option OHLC come from `NEW_PROJ/atm_iv_cache` and `Calendar_Dispersion_BT/cache/opt`. Statutory F&O costs are charged **at mid**. Margins are NSE SPAN XML risk arrays when a clearing zip is cached, else a short-option % proxy plus **ELM 2% index / 3.5% stock** (same rates as Calendar_Dispersion_BT). `--cache-only` never imports `growwapi` or `Calendar_Dispersion_BT`.

## Before any backtest

The runner inspects caches, constituents, events, option OHLC, SPAN zips, and holidays, then writes `cache/data_inventory.md`. It records what **can** and **cannot** be tested. Nothing in that file is fabricated.

Live tape on this machine is **hourly** (09:00–15:00), not 5-minute. Hedges and BS Greeks are **1h** and labeled `hedge_frequency=1h`. There is no bid/ask column and no futures cache; fills are mid±slippage and the hedge underlying is `spot_as_fut_proxy`.

## Two books

1. **Index** — Monday entry, short the next-Tuesday Nifty **ATM-forward** weekly straddle (`F = S·exp(rT)`), minimum 8 DTE, roll the following Monday. Dynamic delta hedge on the 1h clock.
2. **Stocks** — Point-in-time liquid Nifty constituents with F&O. Monthly ATM-forward straddles, each name hedged with the cash/SSF proxy. A name is skipped when an event **date** in `data/events.csv` falls in `[entry, expiry]`.

Event clock: hourly bar, then Monday entry.

## Signal and exits (v2)

- **Signal:** matched-tenor realized vol from native hourly log returns over a window matching the option’s T. Variance ratio `IV²/RV²`. PIT z-score of that ratio on prior Monday 10:00 observations. Enter when ratio ≥ 1.0 and z ≥ 0.5 when history exists (ratio-only if z is still `na`).
- **Variance budget:** `sold_var = σ²T` at entry. Flatten when path realized variance since entry ≥ `sold_var`.
- **Crush TP:** remaining implied variance ≤ 30% of `sold_var` while path RV is still < 50% of the budget.
- **Running-hot:** realized variance rate ≥ 2× the sold variance rate.
- Not an 80% remaining-RV rule.

Size is stress-loss: lots such that a 1.75× expected-move restress stays inside 20% of posted capital (₹25 lakh default).

## Backtests A–H

| ID | Book | Hedge | Var-ratio filter | Variance budget | Event-in-life |
|----|------|-------|------------------|-----------------|---------------|
| A | Index weekly | no | always-in | no | — |
| B | Index weekly | 1h | always-in | no | — |
| C | Index weekly | 1h | yes | no | — |
| D | Index weekly | 1h | yes | yes | — |
| E | Stock monthly | no | always-in | no | no |
| F | Stock monthly | 1h | always-in | no | no |
| G | Stock monthly | 1h | always-in | no | yes |
| H | Stock monthly | 1h | yes | yes | yes |

## IS / validation / OOS

Groww 1h history is capped near **180 calendar days** (~120 sessions, ~25 Mondays). That is **too short** for a three-way split. The runner writes `cache/split_disclaimer.md` instead of fabricating folds.

## Run

From the `realized_vol` repo root (Groww keys in `NEW_PROJ/api_keys.json` only if you are not cache-only):

```bash
python3 -m Index_Stock_VRP.run --cache-only --lookback 180
python3 -m Index_Stock_VRP.run --config Index_Stock_VRP/configs/default.json --cache-only
python3 -m Index_Stock_VRP.run --synthetic --paper --stress
python3 -m unittest Index_Stock_VRP.tests.test_vrp
```

`--cache-only` must not require `growwapi`. Use the repo `.venv` if that is the interpreter without the package.

## Outputs

Under `Index_Stock_VRP/cache/`:

- `data_inventory.md` / `data_inventory.json` (written **before** A–H)
- `{A–H}/trades.csv`, `hourly.csv`, `daily.csv`, `risk.csv`, `skips.csv`
- `charts/{id}_equity.png`, `{id}_vrp_pnl.png`, `AH_total_pnl.png`
- `split_disclaimer.md`, `stress/stress_summary.csv`
- `paper_blotter.csv` (last bar, books D and H)

CSV columns are fixed in `schemas.py` (`TRADES`, `HOURLY`, `DAILY`, `RISK`, `SKIPS`).

Paper trading is a blotter, not a live loop.

## Config

JSON at `configs/default.json` (YAML copy at `configs/default.yaml`). Pass `--config path`. PyYAML is optional; JSON always works.

## 26 sections

1. Independent Index and Stock books, no dispersion.
2. Disk inventory before any backtest; can/cannot-test written to disk.
3. PIT universe: membership ∩ liquid F&O.
4. Session calendar from native 1h bars; holiday gaps inferred from missing weekdays.
5. ATM-forward strikes `F=S·exp(rT)`, not spot ATM.
6. Index: Monday / next Tuesday weekly / ≥8 DTE / roll next Monday.
7. Stock: monthly 21–45 DTE, flatten at 7 DTE.
8. PIT as-of filters; no lookahead on IV/RV.
9. Execution: bid/ask if present, else mid±slippage.
10. NSE F&O statutory costs at mids (STT 0.15% option sell, stamp 0.003% buy, NSE/SEBI/GST).
11. SPAN XML + ELM 2%/3.5%; no `nse_span` import on cache-only.
12. Event-driven hourly engine (bar then entry).
13. Matched-tenor `IV²/RV²` and PIT z-score.
14. Remaining-variance budget, crush TP, running-hot.
15. Native **1h** hedge, labeled; not 5-minute Greeks.
16. Stress-loss sizing 1.75× EM ≤ 20% of ₹25 lakh.
17. Event-in-life exclusion `[entry, expiry]`, not T−2/T+1.
18. YAML/JSON config.
19. `trades.csv` schema.
20. `hourly.csv` schema.
21. `daily.csv` schema.
22. `risk.csv` schema.
23. Stress tests (jump, crush, missing tape, event rule, full budget).
24. IS/validation/OOS: too short on 180d; disclaimer file.
25. Paper blotter from last bar.
26. Charts, unit tests, this README, `--cache-only` without growwapi.

## Point-in-time data

- Nifty membership: `data/nifty50_membership.csv` (`start`/`end`).
- Events: `data/events.csv` — typical FY26/FY27 windows, **not** an announcement tape. Replace before relying on G/H.
- Option fills need a 1h mid on the contract. Index never substitutes a later expiry when the intended Tuesday tape is missing; it waits 11:00 … 15:00 the same Monday.
- Groww 1h history is capped at ~180 calendar days.

## Layout

```
Index_Stock_VRP/
  configs/default.json
  config.py
  inventory.py
  engine.py
  variance.py
  calendar_events.py
  span_elm.py
  schemas.py
  splits.py
  stress.py
  source.py
  ...
```
