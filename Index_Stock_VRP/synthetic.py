"""Synthetic hourly tape for the two-book engine."""

from __future__ import annotations

from datetime import datetime

import numpy as np
import pandas as pd

from . import config as C
from .pricing import atm_forward_strike, nearest_strike, straddle_unit, years_to

STOCKS = ["HDFCBANK", "INFY", "RELIANCE"]
START = pd.Timestamp("2026-03-02 09:00:00")
WEEKS = 10
HOURS = range(9, 16)
SPOT0 = {"NIFTY": 24000.0, "HDFCBANK": 920.0, "INFY": 1580.0, "RELIANCE": 1380.0}
BETA = {"HDFCBANK": 1.05, "INFY": 0.85, "RELIANCE": 1.10}
IV = {"NIFTY": 0.16, "HDFCBANK": 0.22, "INFY": 0.24, "RELIANCE": 0.28}


def _exp_token(expiry: str) -> str:
    return pd.Timestamp(expiry).strftime("%d%b%y")


def _gsym(symbol: str, expiry: str, k: float, opt: str) -> str:
    ks = str(int(k)) if float(k).is_integer() else f"{k:g}"
    return f"NSE-{symbol}-{_exp_token(expiry)}-{ks}-{opt}"


class SyntheticSource:
    def __init__(self, seed: int = 7):
        rng = np.random.default_rng(seed)
        self.ts: list[pd.Timestamp] = []
        d = START.normalize()
        end = START + pd.Timedelta(weeks=WEEKS)
        while d <= end:
            if int(d.weekday()) < 5:
                self.ts.extend(d + pd.Timedelta(hours=h) for h in HOURS)
            d += pd.Timedelta(days=1)
        days = sorted({t.normalize() for t in self.ts})
        self._expiries = [d.strftime("%Y-%m-%d") for d in days if int(d.weekday()) == 1]
        self._lots = dict(C.DEFAULT_LOTS)
        self._steps = dict(C.DEFAULT_STEPS)
        self._ohlc: dict[str, pd.DataFrame] = {}
        nifty = self._gbm(SPOT0["NIFTY"], 0.12, rng)
        self._iv = {C.INDEX: self._iv_path(IV[C.INDEX], rng)}
        self._panels = {C.INDEX: self._panel(C.INDEX, nifty, self._iv[C.INDEX])}
        r_i = np.diff(np.log(nifty), prepend=np.log(nifty[0]))
        dt = 1.0 / (C.TRADING_DAYS * C.NATIVE_BARS_PER_DAY)
        for s in STOCKS:
            idio = rng.normal(0.0, 0.18 * np.sqrt(dt), size=len(nifty))
            px = SPOT0[s] * np.exp(np.cumsum(BETA[s] * r_i + idio))
            self._iv[s] = self._iv_path(IV[s], rng)
            self._panels[s] = self._panel(s, px, self._iv[s])
        self._build_option_tape()

    def _iv_path(self, base: float, rng) -> np.ndarray:
        n = len(self.ts)
        wave = 0.18 * np.sin(np.linspace(0, 4 * np.pi, n))
        noise = rng.normal(0.0, 0.02, size=n)
        iv = base * (1.0 + wave + noise)
        w0 = self.ts[0].isocalendar().week
        for i, t in enumerate(self.ts):
            if t.isocalendar().week == w0 + 3:
                iv[i] *= 0.55
        return np.clip(iv, 0.08, 0.60)

    def _gbm(self, s0: float, vol: float, rng) -> np.ndarray:
        dt = 1.0 / (C.TRADING_DAYS * C.NATIVE_BARS_PER_DAY)
        shocks = rng.normal(0.0, vol * np.sqrt(dt), size=len(self.ts))
        w0 = self.ts[0].isocalendar().week
        for i, t in enumerate(self.ts):
            if t.isocalendar().week == w0 + 6 and t.hour == 11:
                shocks[i] -= 0.025
        return np.exp(np.log(s0) + np.cumsum(shocks))

    def _front_expiry(self, ts: pd.Timestamp, symbol: str) -> str:
        need = C.MIN_DTE if symbol == C.INDEX else C.STOCK_MIN_DTE
        for e in self._expiries:
            if (pd.Timestamp(e).normalize() - ts.normalize()).days >= need:
                return e
        return self._expiries[-1]

    def _panel(self, symbol: str, spots: np.ndarray, ivs: np.ndarray) -> pd.DataFrame:
        step = self._steps.get(symbol, 5.0)
        rows = []
        for ts, s, iv in zip(self.ts, spots, ivs):
            exp = self._front_expiry(ts, symbol)
            rows.append(
                dict(
                    timestamp=ts,
                    spot=float(s),
                    expiry_date=exp,
                    atm_strike=atm_forward_strike(float(s), years_to(ts, exp), step=step),
                    atm_iv=float(iv) * 100.0,
                )
            )
        return pd.DataFrame(rows)

    def _build_option_tape(self) -> None:
        buckets: dict[str, list] = {}
        for symbol, panel in self._panels.items():
            step = self._steps.get(symbol, 5.0)
            for _, r in panel.iterrows():
                ts = pd.Timestamp(r["timestamp"])
                iv = float(r["atm_iv"]) / 100.0
                for exp in self._expiries:
                    if ts.normalize() > pd.Timestamp(exp):
                        continue
                    t = years_to(ts, exp)
                    k = atm_forward_strike(float(r["spot"]), t, step=step)
                    g = straddle_unit(float(r["spot"]), k, t, iv)
                    for opt, px in (("CE", g["ce"]), ("PE", g["pe"])):
                        gsym = _gsym(symbol, exp, k, opt)
                        buckets.setdefault(gsym, []).append((ts, px))
        for gsym, rows in buckets.items():
            idx = pd.to_datetime([t for t, _ in rows])
            px = [p for _, p in rows]
            df = pd.DataFrame({"open": px, "high": px, "low": px, "close": px}, index=idx)
            self._ohlc[gsym] = df[~df.index.duplicated(keep="last")].sort_index()

    def panel(self, symbol: str) -> pd.DataFrame:
        symbol = symbol.upper()
        if symbol not in self._panels:
            raise FileNotFoundError(f"no synthetic panel for {symbol}")
        return self._panels[symbol]

    def expiries(self, symbol: str) -> list[str]:
        return list(self._expiries)

    def contracts(self, symbol: str, expiry: str) -> dict[float, dict[str, str]]:
        out: dict[float, dict[str, str]] = {}
        prefix = f"NSE-{symbol.upper()}-{_exp_token(expiry)}-"
        for gsym in self._ohlc:
            if gsym.startswith(prefix):
                parts = gsym.split("-")
                out.setdefault(float(parts[-2]), {})[parts[-1]] = gsym
        return out

    def option_ohlc(self, groww_symbol: str, start: datetime, end: datetime) -> pd.DataFrame:
        df = self._ohlc.get(groww_symbol)
        if df is None or df.empty:
            return pd.DataFrame(columns=["open", "high", "low", "close"])
        a, b = pd.Timestamp(start), pd.Timestamp(end)
        return df[(df.index >= a) & (df.index <= b)]

    def lot_size(self, symbol: str) -> int:
        return int(self._lots.get(symbol.upper(), 1))

    def strike_step(self, symbol: str) -> float:
        return float(self._steps.get(symbol.upper(), 5.0))

    def option_symbol(self, symbol: str, expiry: str, k: float, opt: str) -> str | None:
        cmap = self.contracts(symbol, expiry)
        if not cmap:
            return None
        kk = nearest_strike(list(cmap), k)
        return cmap.get(kk, {}).get("CE" if opt == "call" else "PE")
