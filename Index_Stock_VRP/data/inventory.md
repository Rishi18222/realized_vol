# Data inventory (before backtest)

Inspected on disk. Nothing below is fabricated.

- Hedge frequency: **1h** (not 5-minute).
- Hedge underlying: **spot_as_fut_proxy**.
- ATM v6 180d panels: 17.
- Option OHLC pickles: 2375; underlyings: AXISBANK, BAJFINANCE, BHARTIARTL, HDFCBANK, ICICIBANK, INFY, ITC, KOTAKBANK, LT, NIFTY, RELIANCE, SBIN, TCS.
- SPAN zips: 55 (nsccl.20260330.s.zip → nsccl.20260916.s.zip).
- Futures caches: none.
- Holiday files in package data: none (gaps from missing weekday bars).

## Panels

| symbol | rows | start | end | hours | nan IV | bid/ask | rv cols |
|---|---:|---|---|---|---:|---|---|
| AXISBANK | 842 | 2026-03-23 09:00:00 | 2026-09-17 10:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.0 | False | ['rv_7h', 'rv_14h', 'rv_21h', 'rv_28h', 'rv_35h'] |
| BAJAJFINSV | 840 | 2026-01-05 09:00:00 | 2026-07-02 15:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.030952380952380953 | False | [] |
| BAJFINANCE | 842 | 2026-03-23 09:00:00 | 2026-09-17 10:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.0 | False | ['rv_7h', 'rv_14h', 'rv_21h', 'rv_28h', 'rv_35h'] |
| BHARTIARTL | 840 | 2026-03-23 09:00:00 | 2026-09-16 15:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.0 | False | ['rv_7h', 'rv_14h', 'rv_21h', 'rv_28h', 'rv_35h'] |
| GRASIM | 840 | 2026-01-05 09:00:00 | 2026-07-02 15:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.039285714285714285 | False | [] |
| HDFCBANK | 840 | 2026-03-23 09:00:00 | 2026-09-16 15:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.0 | False | ['rv_7h', 'rv_14h', 'rv_21h', 'rv_28h', 'rv_35h'] |
| ICICIBANK | 840 | 2026-03-23 09:00:00 | 2026-09-16 15:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.0 | False | ['rv_7h', 'rv_14h', 'rv_21h', 'rv_28h', 'rv_35h'] |
| INFY | 840 | 2026-03-23 09:00:00 | 2026-09-16 15:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.07380952380952381 | False | ['rv_7h', 'rv_14h', 'rv_21h', 'rv_28h', 'rv_35h'] |
| ITC | 840 | 2026-03-23 09:00:00 | 2026-09-16 15:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.030952380952380953 | False | ['rv_7h', 'rv_14h', 'rv_21h', 'rv_28h', 'rv_35h'] |
| KOTAKBANK | 842 | 2026-03-23 09:00:00 | 2026-09-17 10:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.004750593824228029 | False | ['rv_7h', 'rv_14h', 'rv_21h', 'rv_28h', 'rv_35h'] |
| LT | 840 | 2026-03-23 09:00:00 | 2026-09-16 15:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.005952380952380952 | False | ['rv_7h', 'rv_14h', 'rv_21h', 'rv_28h', 'rv_35h'] |
| NIFTY | 841 | 2026-03-23 09:00:00 | 2026-09-17 09:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.041617122473246136 | False | ['rv_7h', 'rv_14h', 'rv_21h', 'rv_28h', 'rv_35h'] |
| NMDC | 840 | 2026-01-05 09:00:00 | 2026-07-02 15:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.07738095238095238 | False | [] |
| NTPC | 840 | 2026-01-05 09:00:00 | 2026-07-02 15:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.04642857142857143 | False | [] |
| RELIANCE | 840 | 2026-03-23 09:00:00 | 2026-09-16 15:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.0 | False | ['rv_7h', 'rv_14h', 'rv_21h', 'rv_28h', 'rv_35h'] |
| SBIN | 842 | 2026-03-23 09:00:00 | 2026-09-17 10:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.0 | False | ['rv_7h', 'rv_14h', 'rv_21h', 'rv_28h', 'rv_35h'] |
| TCS | 840 | 2026-03-23 09:00:00 | 2026-09-16 15:00:00 | [9, 10, 11, 12, 13, 14, 15] | 0.0 | False | ['rv_7h', 'rv_14h', 'rv_21h', 'rv_28h', 'rv_35h'] |

## Can test

- Index weekly ATM-forward straddles on NIFTY 1h ATM-IV + option OHLC (Groww ~180d).
- Stock monthly ATM-forward straddles on liquid F&O names that have both an ATM panel and option cache.
- Fills at option OHLC close as mid, plus configured slippage (no bid/ask tape).
- Statutory NSE F&O costs charged on mid premium.
- SPAN XML risk arrays on 55 cached clearing zips; ELM 2% index / 3.5% stock otherwise.
- Delta hedge on the native 1h clock using spot as the futures proxy.
- Matched-tenor IV²/RV², remaining-variance budget, crush and running-hot exits.
- Event-in-life skips using data/events.csv dates inside [entry, expiry].
- Stress-loss lot cap (1.75× EM vs 20% of posted capital).
- --cache-only from pickle ATM-IV and option OHLC without growwapi.

## Cannot test

- 5-minute Greeks or 5-minute hedges: every panel and option file is hourly (09:00–15:00). Hedge frequency is labeled 1h.
- True bid/ask execution: ATM panels and sampled option OHLC have no bid/ask columns. Engine uses mid±slippage and records fill_source=mid+slip.
- True futures/SSF marks: no futures cache is present. Hedge P&L uses spot as a futures proxy and is labeled spot_as_fut_proxy.
- PIT earnings announcement dates: data/events.csv is an illustrative research calendar (typical FY26/FY27 windows), not an announcement tape.
- Full Nifty 50 option book: option OHLC underlyings are the 12 liquid F&O names plus NIFTY. Extra ATM panels (BAJAJFINSV, GRASIM, NMDC, NTPC) are not in LIQUID_FNO.
- Official holiday calendar file: none in-package; session gaps are inferred from missing weekday bars.
- IS / validation / OOS: Groww history is capped near 180 calendar days (~121 NIFTY sessions, ~24 Mondays). Too short for a three-way split.

## IS / validation / OOS

Groww 1h history ~180d is too short for in-sample / validation / out-of-sample. NIFTY sessions=121, Mondays≈24.

