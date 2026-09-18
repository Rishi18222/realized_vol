# Data inventory (before backtest)

Inspected on disk. Nothing below is fabricated.

- Hedge frequency: **1h** (not 5-minute).
- Hedge underlying: **spot_as_fut_proxy**.
- ATM v6 180d panels: 17.
- Option OHLC pickles: 2375; underlyings: AXISBANK, BAJFINANCE, BHARTIARTL, HDFCBANK, ICICIBANK, INFY, ITC, KOTAKBANK, LT, NIFTY, RELIANCE, SBIN, TCS.
- SPAN zips: 55 (nsccl.20260330.s.zip → nsccl.20260916.s.zip).
- Futures caches: none.
- Holiday files in package data: none (gaps from missing weekday bars).
- Membership names in file: 49.

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
- Stock monthly ATM-forward straddles on PIT Nifty 50 names that have both an ATM panel and option cache. Others are recorded as skips.
- Long or short vol from implied forward variance vs 5/20/60/120 forecast RV after costs/buffers.
- Fills at option OHLC close as mid, plus configured slippage (no bid/ask tape).
- Statutory NSE F&O costs charged on mid premium.
- SPAN XML risk arrays on 55 cached clearing zips; ELM 2% index / 3.5% stock otherwise.
- Delta hedge on the native 1h clock: Nifty spot proxy for the index book, own-stock spot proxy for each stock.
- --cache-only from pickle ATM-IV and option OHLC without growwapi.

## Cannot test

- 5-minute Greeks or 5-minute hedges: every panel and option file is hourly (09:00–15:00). Hedge frequency is labeled 1h.
- True bid/ask execution: ATM panels and sampled option OHLC have no bid/ask columns. Engine uses mid±slippage and records fill_source=mid+slip.
- True futures/SSF marks: no futures cache is present. Hedge P&L uses spot as a futures proxy and is labeled spot_as_fut_proxy (index) or {symbol}_spot_proxy (stocks).
- PIT earnings announcement dates: data/events.csv is an illustrative research calendar, not an announcement tape.
- Full Nifty 50 option book: option OHLC underlyings are ['AXISBANK', 'BAJFINANCE', 'BHARTIARTL', 'HDFCBANK', 'ICICIBANK', 'INFY', 'ITC', 'KOTAKBANK', 'LT', 'NIFTY', 'RELIANCE', 'SBIN', 'TCS']. Names without tape are skipped, not fabricated.
- A 50th PIT name beyond the membership file (49 unique symbols): the missing constituent is not invented.
- Official holiday calendar file: none in-package; session gaps are inferred from missing weekday bars.
- 120-day RV for most of the sample: Groww ~180 calendar days ≈ 121 sessions, so the 120 window is usually missing and weights renormalize. Nothing is filled in.
- Out-of-sample / validation split: Groww history is capped near 180 calendar days (~121 NIFTY sessions). Too short. Do not claim OOS.

## Forecast RV / OOS

Groww 1h history ~180d is too short for in-sample / validation / out-of-sample. NIFTY sessions=121, Mondays≈24.

