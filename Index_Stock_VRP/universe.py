"""Point-in-time Nifty 50 membership. Every name is scanned; tape gaps are skips."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config as C


def load_membership(path: Path | None = None) -> pd.DataFrame:
    p = path or (C.DATA_DIR / "nifty50_membership.csv")
    df = pd.read_csv(p)
    df["symbol"] = df["symbol"].astype(str).str.upper()
    df["start"] = pd.to_datetime(df["start"])
    df["end"] = pd.to_datetime(df["end"])
    return df


def constituents_asof(asof, *, membership: pd.DataFrame | None = None) -> list[str]:
    m = membership if membership is not None else load_membership()
    d = pd.Timestamp(asof).normalize()
    live = m[(m["start"] <= d) & (m["end"] >= d)]
    return sorted(live["symbol"].unique().tolist())


def tradeable_asof(asof, *, membership: pd.DataFrame | None = None) -> list[str]:
    """Every PIT Nifty 50 member. Missing option tape is a skip, not a filter here."""
    return constituents_asof(asof, membership=membership)
