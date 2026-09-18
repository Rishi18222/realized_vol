"""Market data: disk caches by default; Groww I/O is lazy and live-only."""

from __future__ import annotations

import pickle
import re
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C

ATM_CACHE = C.REPO_ROOT / "NEW_PROJ" / "atm_iv_cache"
OPT_CACHE = C.REPO_ROOT / "Calendar_Dispersion_BT" / "cache" / "opt"

_EXPIRY_TOKEN = re.compile(r"NSE-([A-Z0-9&]+)-(\d{1,2}[A-Za-z]{3}\d{2})-")
_OPT_SYM = re.compile(r"NSE-[^-]+-\d{1,2}[A-Za-z]{3}\d{2}-([\d.]+)-(CE|PE)$")
_gio = None


def parse_groww_option_symbol(sym: str) -> tuple[float | None, str | None]:
    m = _OPT_SYM.match(sym)
    if not m:
        return None, None
    return float(m.group(1)), m.group(2)


def is_monthly_expiry(expiry: str) -> bool:
    d = pd.Timestamp(expiry).date()
    return (d + timedelta(days=7)).month != d.month


def daily_close(panel: pd.DataFrame) -> pd.Series:
    df = panel.dropna(subset=["spot"]).copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.normalize()
    return df.groupby("date")["spot"].last().sort_index()


def row_at(panel: pd.DataFrame, ts: pd.Timestamp) -> pd.Series | None:
    df = panel.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    hit = df[df["timestamp"] == pd.Timestamp(ts)]
    if hit.empty:
        hit = df[df["timestamp"] <= pd.Timestamp(ts)]
        if hit.empty:
            return None
        return hit.iloc[-1]
    return hit.iloc[-1]


def strike_step(strikes: list[float], default: float = 5.0) -> float:
    uniq = sorted(set(float(k) for k in strikes))
    if len(uniq) < 2:
        return default
    gaps = np.diff(uniq)
    vals, counts = np.unique(np.round(gaps, 6), return_counts=True)
    step = float(vals[int(np.argmax(counts))])
    return step if step > 0 else default


def _expiry_from_token(tok: str) -> str | None:
    try:
        return pd.to_datetime(tok, format="%d%b%y").strftime("%Y-%m-%d")
    except Exception:
        return None


def _live_gio():
    """Import Groww helpers only for live/refetch runs. Requires growwapi."""
    global _gio
    if _gio is None:
        from Calendar_Dispersion_BT import groww_io as gio  # noqa: WPS433

        _gio = gio
    return _gio


def load_cached_iv_panel(symbol: str, lookback_days: int) -> pd.DataFrame:
    """Read NEW_PROJ/atm_iv_cache pickles. No GrowwAPI."""
    symbol = symbol.upper()
    names: list[Path] = []
    for ver in ("v6", "v5", "v4", "v3"):
        names.append(ATM_CACHE / f"{symbol}_{int(lookback_days)}d_1h_{ver}.pkl")
    if ATM_CACHE.exists():
        names.extend(sorted(ATM_CACHE.glob(f"{symbol}_*d_1h_v6.pkl"), reverse=True))
        names.extend(sorted(ATM_CACHE.glob(f"{symbol}_*d_1h_v5.pkl"), reverse=True))
        names.extend(sorted(ATM_CACHE.glob(f"{symbol}_*d_1h.pkl"), reverse=True))
    seen: set[Path] = set()
    for path in names:
        if path in seen or not path.exists():
            continue
        seen.add(path)
        try:
            with path.open("rb") as f:
                obj = pickle.load(f)
        except Exception:
            continue
        panel = obj.get("panel") if isinstance(obj, dict) else obj
        if isinstance(panel, pd.DataFrame) and not panel.empty and "spot" in panel.columns:
            out = panel.copy()
            out["timestamp"] = pd.to_datetime(out["timestamp"])
            return out
    raise FileNotFoundError(f"no ATM-IV cache for {symbol} under {ATM_CACHE}")


class GrowwSource:
    """Hourly ATM panels + option OHLC. Cache-only never imports growwapi."""

    def __init__(self, *, lookback_days: int = C.LOOKBACK_DAYS, refetch: bool = False, cache_only: bool = False):
        self.lookback_days = int(lookback_days)
        self.refetch = bool(refetch)
        self.cache_only = bool(cache_only)
        self._groww = None
        self._panels: dict[str, pd.DataFrame] = {}
        self._expiries: dict[str, list[str]] = {}
        self._contracts: dict[tuple[str, str], dict[float, dict[str, str]]] = {}
        self._ohlc: dict[str, pd.DataFrame] = {}
        self._lots: dict[str, int] = dict(C.DEFAULT_LOTS)
        self._steps: dict[str, float] = dict(C.DEFAULT_STEPS)

    @property
    def groww(self):
        if self.cache_only:
            return None
        if self._groww is None:
            self._groww = _live_gio().client()
        return self._groww

    def panel(self, symbol: str) -> pd.DataFrame:
        symbol = symbol.upper()
        if symbol not in self._panels:
            if self.cache_only or not self.refetch:
                try:
                    self._panels[symbol] = load_cached_iv_panel(symbol, self.lookback_days)
                    return self._panels[symbol]
                except FileNotFoundError:
                    if self.cache_only:
                        raise
            roll = 0 if symbol == C.INDEX else 7
            gio = _live_gio()
            self._panels[symbol] = gio.hourly_panel(
                symbol,
                self.groww,
                lookback_days=self.lookback_days,
                roll_days=roll,
                refetch=self.refetch,
            )
        return self._panels[symbol]

    def expiries(self, symbol: str) -> list[str]:
        symbol = symbol.upper()
        if symbol in self._expiries:
            return self._expiries[symbol]
        found: set[str] = set()
        if not self.cache_only:
            try:
                found.update(_live_gio().list_expiries(self.groww, symbol, self.lookback_days))
            except Exception:
                pass
        panel = self.panel(symbol)
        if "expiry_date" in panel.columns:
            for e in panel["expiry_date"].dropna().astype(str):
                if len(e) >= 8:
                    found.add(str(e)[:10])
        found.update(self._expiries_from_opt_cache(symbol))
        self._expiries[symbol] = sorted(found)
        return self._expiries[symbol]

    def _expiries_from_opt_cache(self, symbol: str) -> set[str]:
        out: set[str] = set()
        if not OPT_CACHE.exists():
            return out
        prefix = f"NSE-{symbol}-"
        for p in OPT_CACHE.glob(f"{prefix}*"):
            m = _EXPIRY_TOKEN.match(p.name)
            if not m:
                continue
            exp = _expiry_from_token(m.group(2))
            if exp:
                out.add(exp)
        return out

    def contracts(self, symbol: str, expiry: str) -> dict[float, dict[str, str]]:
        key = (symbol.upper(), str(expiry)[:10])
        if key in self._contracts:
            return self._contracts[key]
        cmap: dict[float, dict[str, str]] = {}
        if not self.cache_only:
            try:
                cmap = _live_gio().contracts_by_strike(self.groww, symbol, expiry)
            except Exception:
                cmap = {}
        if not cmap:
            cmap = self._contracts_from_opt_cache(symbol, expiry)
        self._contracts[key] = cmap
        if cmap:
            default = C.DEFAULT_STEPS.get(symbol.upper(), 5.0)
            self._steps[symbol.upper()] = strike_step(list(cmap), default=default)
        return cmap

    def _contracts_from_opt_cache(self, symbol: str, expiry: str) -> dict[float, dict[str, str]]:
        token = pd.Timestamp(expiry).strftime("%d%b%y")
        out: dict[float, dict[str, str]] = {}
        if not OPT_CACHE.exists():
            return out
        for p in OPT_CACHE.glob(f"NSE-{symbol.upper()}-*{token.upper()}*"):
            gsym = p.name.split("_")[0]
            strike, otype = parse_groww_option_symbol(gsym)
            if strike is None or otype is None:
                continue
            out.setdefault(float(strike), {})[otype] = gsym
        if out:
            return out
        for p in OPT_CACHE.glob(f"NSE-{symbol.upper()}-*"):
            gsym = p.name.split("_")[0]
            m = _EXPIRY_TOKEN.match(gsym)
            if not m:
                continue
            parsed = _expiry_from_token(m.group(2))
            if parsed != str(expiry)[:10]:
                continue
            strike, otype = parse_groww_option_symbol(gsym)
            if strike is None or otype is None:
                continue
            out.setdefault(float(strike), {})[otype] = gsym
        return out

    def option_ohlc(self, groww_symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        stitched = self._symbol_ohlc(groww_symbol)
        if stitched is not None and not stitched.empty:
            a = pd.Timestamp(start).tz_localize(None)
            b = pd.Timestamp(end).tz_localize(None)
            hit = stitched[(stitched.index >= a) & (stitched.index <= b)]
            if not hit.empty:
                return hit
        if self.cache_only:
            return stitched if stitched is not None else pd.DataFrame(columns=["open", "high", "low", "close"])
        df = _live_gio().option_ohlc(self.groww, groww_symbol, start, end)
        if df is not None and not df.empty:
            self._merge_ohlc(groww_symbol, df)
        return df if df is not None else pd.DataFrame(columns=["open", "high", "low", "close"])

    def _symbol_ohlc(self, groww_symbol: str) -> pd.DataFrame:
        if groww_symbol in self._ohlc:
            return self._ohlc[groww_symbol]
        frames: list[pd.DataFrame] = []
        if OPT_CACHE.exists():
            safe = groww_symbol.replace("/", "_")
            for p in list(OPT_CACHE.glob(f"{safe}_*_ohlc.pkl")) + list(OPT_CACHE.glob(f"{safe}_*.pkl")):
                try:
                    df = pd.read_pickle(p)
                except Exception:
                    continue
                if df is None or getattr(df, "empty", True):
                    continue
                if isinstance(df, pd.Series):
                    df = df.to_frame(name="close")
                if "timestamp" in df.columns:
                    df = df.set_index(pd.to_datetime(df["timestamp"]))
                df.index = pd.to_datetime(df.index).tz_localize(None)
                cols = [c for c in ("open", "high", "low", "close") if c in df.columns]
                if "close" not in cols and len(df.columns):
                    df = df.rename(columns={df.columns[-1]: "close"})
                    cols = [c for c in ("open", "high", "low", "close") if c in df.columns]
                if "close" not in cols:
                    continue
                frames.append(df[cols])
        if frames:
            out = pd.concat(frames).sort_index()
            out = out[~out.index.duplicated(keep="last")]
        else:
            out = pd.DataFrame(columns=["open", "high", "low", "close"])
        self._ohlc[groww_symbol] = out
        return out

    def _merge_ohlc(self, groww_symbol: str, df: pd.DataFrame) -> None:
        cur = self._ohlc.get(groww_symbol)
        add = df.copy()
        add.index = pd.to_datetime(add.index).tz_localize(None)
        if cur is None or cur.empty:
            self._ohlc[groww_symbol] = add
            return
        merged = pd.concat([cur, add]).sort_index()
        self._ohlc[groww_symbol] = merged[~merged.index.duplicated(keep="last")]

    def lot_size(self, symbol: str) -> int:
        return int(self._lots.get(symbol.upper(), 1))

    def strike_step(self, symbol: str) -> float:
        return float(self._steps.get(symbol.upper(), 5.0))

    def option_symbol(self, symbol: str, expiry: str, k: float, opt: str) -> str | None:
        cmap = self.contracts(symbol, expiry)
        if not cmap:
            return None
        from .pricing import nearest_strike

        kk = nearest_strike(list(cmap), k)
        return cmap.get(kk, {}).get("CE" if opt == "call" else "PE")
