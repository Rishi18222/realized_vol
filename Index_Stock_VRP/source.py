"""Market data: Groww + local option/IV caches. Point-in-time panels only."""

from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd

from . import config as C

_NEW = str(C.REPO_ROOT / "NEW_PROJ")
if _NEW not in sys.path:
    sys.path.insert(0, _NEW)

from Calendar_Dispersion_BT import groww_io as gio  # noqa: E402
from Calendar_Dispersion_BT import config as CD  # noqa: E402
from underlying_vrp_pipeline import parse_groww_option_symbol  # noqa: E402

_EXPIRY_TOKEN = re.compile(r"NSE-([A-Z0-9&]+)-(\d{1,2}[A-Za-z]{3}\d{2})-")


def is_monthly_expiry(expiry: str) -> bool:
    d = pd.Timestamp(expiry).date()
    return (d + timedelta(days=7)).month != d.month


def daily_close(panel: pd.DataFrame) -> pd.Series:
    df = panel.dropna(subset=["spot"]).copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["date"] = df["timestamp"].dt.normalize()
    return df.groupby("date")["spot"].last().sort_index()


def row_at(panel: pd.DataFrame, ts: pd.Timestamp) -> pd.Series | None:
    return gio.row_at(panel, ts)


def _expiry_from_token(tok: str) -> str | None:
    try:
        return pd.to_datetime(tok, format="%d%b%y").strftime("%Y-%m-%d")
    except Exception:
        return None


class GrowwSource:
    """Hourly ATM panels + option OHLC. Prefers disk cache; Groww only on miss."""

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
            self._groww = gio.client()
        return self._groww

    def panel(self, symbol: str) -> pd.DataFrame:
        symbol = symbol.upper()
        if symbol not in self._panels:
            roll = 0 if symbol == C.INDEX else 7
            if self.cache_only:
                from underlying_vrp_pipeline import build_underlying_panel

                self._panels[symbol] = build_underlying_panel(
                    symbol,
                    groww=None,
                    lookback_days=self.lookback_days,
                    roll_days=roll,
                    refetch=False,
                    use_cache=True,
                    allow_stale=True,
                    max_cache_age_hours=24 * 400,
                )
            else:
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
                found.update(gio.list_expiries(self.groww, symbol, self.lookback_days))
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
        opt = CD.CACHE_DIR / "opt"
        if not opt.exists():
            return out
        prefix = f"NSE-{symbol}-"
        for p in opt.glob(f"{prefix}*"):
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
                cmap = gio.contracts_by_strike(self.groww, symbol, expiry)
            except Exception:
                cmap = {}
        if not cmap:
            cmap = self._contracts_from_opt_cache(symbol, expiry)
        self._contracts[key] = cmap
        if cmap:
            from Calendar_Dispersion_BT.groww_io import strike_step

            default = C.DEFAULT_STEPS.get(symbol.upper(), 5.0)
            self._steps[symbol.upper()] = strike_step(list(cmap), default=default)
        return cmap

    def _contracts_from_opt_cache(self, symbol: str, expiry: str) -> dict[float, dict[str, str]]:
        exp_ts = pd.Timestamp(expiry)
        token = exp_ts.strftime("%d%b%y")
        # Groww uses 01Sep26 and 1Sep26; glob both.
        opt = CD.CACHE_DIR / "opt"
        out: dict[float, dict[str, str]] = {}
        if not opt.exists():
            return out
        for p in opt.glob(f"NSE-{symbol.upper()}-*{token.upper()}*"):
            gsym = p.name.split("_")[0]
            strike, otype = parse_groww_option_symbol(gsym)
            if strike is None or otype is None:
                continue
            out.setdefault(float(strike), {})[otype] = gsym
        if out:
            return out
        for p in opt.glob(f"NSE-{symbol.upper()}-*"):
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
        df = gio.option_ohlc(self.groww, groww_symbol, start, end)
        if df is not None and not df.empty:
            self._merge_ohlc(groww_symbol, df)
        return df if df is not None else pd.DataFrame(columns=["open", "high", "low", "close"])

    def _symbol_ohlc(self, groww_symbol: str) -> pd.DataFrame:
        if groww_symbol in self._ohlc:
            return self._ohlc[groww_symbol]
        opt = CD.CACHE_DIR / "opt"
        frames: list[pd.DataFrame] = []
        if opt.exists():
            safe = groww_symbol.replace("/", "_")
            for p in list(opt.glob(f"{safe}_*_ohlc.pkl")) + list(opt.glob(f"{safe}_*.pkl")):
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
