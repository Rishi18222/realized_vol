"""Corporate-event exclusion: event date inside the option life [entry, expiry]."""

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


def events_in_life(events: pd.DataFrame, symbol: str, entry, expiry) -> pd.DataFrame:
    """Rows whose event date falls in [entry date, expiry date] inclusive."""
    if events is None or events.empty:
        return pd.DataFrame(columns=getattr(events, "columns", ["symbol", "date", "event_type"]))
    a = pd.Timestamp(entry).normalize()
    b = pd.Timestamp(expiry).normalize()
    hit = events[events["symbol"] == str(symbol).upper()].copy()
    if hit.empty:
        return hit
    return hit[(hit["date"] >= a) & (hit["date"] <= b)].reset_index(drop=True)


def blocked(events: pd.DataFrame, symbol: str, entry, expiry) -> bool:
    """True when an event date sits inside the option's life. Not T−2/T+1."""
    return not events_in_life(events, symbol, entry, expiry).empty
