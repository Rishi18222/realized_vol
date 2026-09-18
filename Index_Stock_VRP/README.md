# Index VRP and Stock VRP

Independent **Index VRP** and **Stock VRP** books for Project ALL_VRP. No dispersion in v1.

Reuses Groww hourly ATM-IV panels and option OHLC from `Calendar_Dispersion_BT` / `NEW_PROJ`. Execution is bid/ask when those quotes exist; otherwise **mid ± explicit slippage**. Statutory F&O costs are charged **at mid**. Margins are the same approximate SPAN/ELM proxies used in the calendar-dispersion book.

## Books

1. **Index** — Monday entry, short the next-Tuesday Nifty **ATM-forward** weekly straddle, minimum 8 DTE, roll the following Monday. Dynamic delta hedge with Nifty futures (spot as the futures proxy).
2. **Stocks** — Point-in-time liquid Nifty constituents with F&O. Monthly ATM-forward straddles, each name hedged with the stock/SSF proxy. Earnings and corporate events in `data/events.csv` are blacked out (T−2 through T+1).

Both books share an event-driven engine (hourly bars + Monday entry events). Signals compare ATM IV to 5-day realized vol. Variance remaining exits flatten when realized variance since entry ≥ 80% of implied variance at entry. Size is stress-loss: lots such that a 1.75× expected-move restress stays inside 20% of posted capital (₹25 lakh default).

## Backtests A–H

| ID | Book | Hedge | VRP filter | Variance exit | Ex-events |
|----|------|-------|------------|---------------|-----------|
| A | Index weekly | no | always-in | no | — |
| B | Index weekly | yes | always-in | no | — |
| C | Index weekly | yes | IV − RV ≥ 1pt | no | — |
| D | Index weekly | yes | yes | yes | — |
| E | Stock monthly | no | always-in | no | no |
| F | Stock monthly | yes | always-in | no | no |
| G | Stock monthly | yes | always-in | no | yes |
| H | Stock monthly | yes | yes | yes | yes |

## Run

From the `realized_vol` repo root (Groww keys in `NEW_PROJ/api_keys.json`):

```bash
python3 -m Index_Stock_VRP.run --backtests A,B,C,D,E,F,G,H --lookback 180
python3 -m Index_Stock_VRP.run --cache-only          # disk IV + option caches only
python3 -m Index_Stock_VRP.run --synthetic           # offline GBM tape
python3 -m Index_Stock_VRP.run --synthetic --paper   # plus paper blotter
python3 -m unittest Index_Stock_VRP.tests.test_vrp
```

Outputs under `Index_Stock_VRP/cache/`:

- `{A–H}/trades.csv`, `hourly.csv`, `daily.csv`, `risk.csv`, `skips.csv`
- `charts/{id}_equity.png`, `{id}_vrp_pnl.png`, `AH_total_pnl.png`
- `paper_blotter.csv` (last bar, books D and H)

Paper trading is a blotter, not a live loop: it sizes the Index D and Stock H books off the last hourly bar. Enter only on Mondays when the signal and DTE rules pass.

## Point-in-time data

- Nifty membership: `data/nifty50_membership.csv` (`start`/`end`). Only names that are members **and** in the liquid F&O list are traded.
- Events: `data/events.csv`. Replace dates with a research calendar before relying on G/H.
- Option fills need a 1h mid on the contract. Index never substitutes a later expiry when the intended Tuesday tape is missing; it waits for 11:00 … 15:00 the same Monday.
- Groww 1h history is capped at ~180 calendar days.

## Layout

```
Index_Stock_VRP/
  config.py         # books, slippage, stress, A–H matrix
  engine.py         # event clock, two books
  source.py         # Groww + Calendar_Dispersion_BT caches
  synthetic.py      # offline tape
  pricing.py        # ATM-forward strike, BS marks
  variance.py       # VRP and remaining-variance exit
  execution.py      # bid/ask or mid+slip; costs at mid
  sizing.py         # 1.75× EM stress lots, approx margin
  universe.py       # PIT constituents
  calendar_events.py
  reports.py
  paper.py
  run.py
  data/
```
