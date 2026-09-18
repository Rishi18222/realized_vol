"""Point-in-time Nifty membership ∩ liquid F&O names."""

from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import config as C


def _membership_path() -> Path:
    return C.DATA_DIR / "nifty50_membership.csv"


def load_membership(path: Path | None = None) -> pd.DataFrame:
    p = path or _membership_path()
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
    """PIT index members that are in the liquid F&O book."""
    names = constituents_asof(asof, membership=membership)
    liquid = {s.upper() for s in C.LIQUID_FNO}
    return [s for s in names if s in liquid]
