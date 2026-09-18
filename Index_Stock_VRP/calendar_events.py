"""Earnings and corporate-event blackouts. Point-in-time; no lookahead."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config as C


def load_events(path: Path | None = None) -> pd.DataFrame:
    p = path or (C.DATA_DIR / "events.csv")
    df = pd.read_csv(p)
    df["symbol"] = df["symbol"].astype(str).str.upper()
    df["date"] = pd.to_datetime(df["date"]).dt.normalize()
    df["event_type"] = df["event_type"].astype(str).str.lower()
    return df.sort_values(["symbol", "date"]).reset_index(drop=True)


def blackout_window(event_date, *, before: int = C.EARNINGS_BLACKOUT_BEFORE, after: int = C.EARNINGS_BLACKOUT_AFTER):
    d = pd.Timestamp(event_date).normalize()
    return d - pd.Timedelta(days=before), d + pd.Timedelta(days=after)


def events_in_span(events: pd.DataFrame, symbol: str, start, end) -> pd.DataFrame:
    if events is None or events.empty:
        return events.iloc[0:0] if events is not None else pd.DataFrame()
    a = pd.Timestamp(start).normalize()
    b = pd.Timestamp(end).normalize()
    hit = events[events["symbol"] == str(symbol).upper()].copy()
    if hit.empty:
        return hit
    rows = []
    for _, r in hit.iterrows():
        lo, hi = blackout_window(r["date"])
        if hi < a or lo > b:
            continue
        rows.append(r)
    return pd.DataFrame(rows)


def blocked(events: pd.DataFrame, symbol: str, start, end) -> bool:
    return not events_in_span(events, symbol, start, end).empty
