"""Event-driven Index VRP and Stock VRP simulator."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import config as C
from . import calendar_events as ev
from . import execution as ex
from . import universe as uni
from . import variance as var
from .pricing import atm_forward_strike, dte_days, expected_move, straddle_unit, years_to
from .sizing import lots_for_stress, margin_posted
from .source import GrowwSource, daily_close, is_monthly_expiry, row_at


KIND_ORDER = {"bar": 0, "index_entry": 1, "stock_entry": 2}


@dataclass
class Event:
    ts: pd.Timestamp
    kind: str
    symbol: str = ""


@dataclass
class Position:
    trade_id: str
    book: str
    symbol: str
    expiry: str
    K: float
    lots: int
    lot: int
    ce_sym: str | None
    pe_sym: str | None
    entry_ts: pd.Timestamp
    roll_ts: pd.Timestamp
    ce_open_mid: float
    pe_open_mid: float
    ce_fill: float
    pe_fill: float
    fill_source: str
    iv_entry: float
    spot_entry: float
    impl_var: float
    real_var: float = 0.0
    last_spot: float = 0.0
    fut_units: float = 0.0
    pnl_opt: float = 0.0
    pnl_fut: float = 0.0
    costs: float = 0.0
    vrp: float = float("nan")
    notes: str = ""


@dataclass
class EngineResult:
    trades: pd.DataFrame
    hourly: pd.DataFrame
    daily: pd.DataFrame
    risk: pd.DataFrame
    skips: pd.DataFrame


class Engine:
    def __init__(
        self,
        src: GrowwSource,
        spec: C.BacktestSpec,
        *,
        events_df: pd.DataFrame | None = None,
        membership: pd.DataFrame | None = None,
        capital: float = C.TARGET_CAPITAL,
    ):
        self.src = src
        self.spec = spec
        self.events_df = events_df if events_df is not None else ev.load_events()
        self.membership = membership if membership is not None else uni.load_membership()
        self.capital_budget = float(capital)
        self.positions: dict[str, Position] = {}
        self.closed: list[dict] = []
        self.hourly_rows: list[dict] = []
        self.risk_rows: list[dict] = []
        self.skips: list[dict] = []
        self.dead: set[str] = set()
        self._nifty: pd.DataFrame | None = None
        self._daily: dict[str, pd.Series] = {}

    def nifty(self) -> pd.DataFrame:
        if self._nifty is None:
            self._nifty = self.src.panel(C.INDEX)
        return self._nifty

    def daily(self, symbol: str) -> pd.Series:
        if symbol not in self._daily:
            self._daily[symbol] = daily_close(self.src.panel(symbol))
        return self._daily[symbol]

    def build_events(self) -> list[Event]:
        panel = self.nifty()
        ts_all = sorted(pd.to_datetime(panel["timestamp"]).unique())
        out: list[Event] = []
        for ts in ts_all:
            ts = pd.Timestamp(ts)
            out.append(Event(ts, "bar"))
            if int(ts.weekday()) == C.ROLL_WEEKDAY:
                if self.spec.book == "index" and int(ts.hour) in C.FILL_HOURS:
                    out.append(Event(ts, "index_entry", C.INDEX))
                if self.spec.book == "stock" and int(ts.hour) == C.ROLL_HOUR:
                    out.append(Event(ts, "stock_entry"))
        out.sort(key=lambda e: (e.ts, KIND_ORDER.get(e.kind, 9)))
        return out

    def run(self) -> EngineResult:
        events = self.build_events()
        print(f"[{self.spec.id}] {self.spec.title}  events={len(events)}")
        for e in events:
            if e.kind == "bar":
                self._on_bar(e.ts)
            elif e.kind == "index_entry":
                self._try_index_entry(e.ts)
            elif e.kind == "stock_entry":
                self._try_stock_entries(e.ts)
        for sym in list(self.positions):
            ts = pd.Timestamp(self.nifty()["timestamp"].max())
            self._close(sym, ts, "eod_flatten")
        return self._frames()

    def _on_bar(self, ts: pd.Timestamp) -> None:
        for sym in list(self.positions):
            pos = self.positions[sym]
            panel = self.src.panel(sym if pos.book == "stock" else C.INDEX)
            row = row_at(panel, ts)
            if row is None or pd.isna(row.get("spot")):
                continue
            spot = float(row["spot"])
            iv = float(row["atm_iv"]) / 100.0 if pd.notna(row.get("atm_iv")) else pos.iv_entry
            if pos.last_spot > 0 and spot > 0:
                pos.real_var += float(np.log(spot / pos.last_spot) ** 2)
                pos.pnl_fut += pos.fut_units * (spot - pos.last_spot)
            pos.last_spot = spot
            g = straddle_unit(spot, pos.K, years_to(ts, pos.expiry), iv)
            if self.spec.hedge and int(ts.hour) >= C.HEDGE_OPEN_HOUR:
                target = -g["delta"] * pos.lots * pos.lot
                d_u = target - pos.fut_units
                if abs(d_u) > 1e-6:
                    pos.costs += ex.hedge_cost(spot * abs(d_u), d_u)
                    pos.fut_units = target
            mark = self._straddle_mark(pos, ts, g["price"])
            opt_unreal = pos.lots * pos.lot * (pos.ce_fill + pos.pe_fill - mark)
            self.hourly_rows.append(
                dict(
                    ts=str(ts),
                    backtest=self.spec.id,
                    book=pos.book,
                    symbol=pos.symbol,
                    expiry=pos.expiry,
                    K=pos.K,
                    spot=spot,
                    iv=iv * 100.0,
                    straddle_mark=mark,
                    fut_units=pos.fut_units,
                    real_var=pos.real_var,
                    impl_var=pos.impl_var,
                    pnl_opt_unreal=opt_unreal,
                    pnl_fut=pos.pnl_fut,
                    costs=pos.costs,
                )
            )
            why = self._exit_reason(pos, ts, row, spot, iv)
            if why:
                self._close(sym, ts, why)

    def _exit_reason(self, pos: Position, ts: pd.Timestamp, row: pd.Series, spot: float, iv: float) -> str | None:
        if ts >= pos.roll_ts and int(ts.hour) >= C.ROLL_HOUR:
            return "monday_roll" if pos.book == "index" else "monthly_roll"
        if pos.book == "stock" and dte_days(ts, pos.expiry) <= C.STOCK_EXIT_DTE and int(ts.hour) >= C.ROLL_HOUR:
            return "dte_exit"
        if self.spec.var_exit and var.variance_exhausted(pos.real_var, pos.impl_var):
            return "variance_remaining"
        s_open = float(row.get("spot", spot))
        em = expected_move(pos.spot_entry, pos.iv_entry, max(dte_days(ts, pos.expiry), 1))
        if em > 0 and abs(spot - pos.spot_entry) >= C.EM_MULT * em and ts < pos.roll_ts:
            return "em_stress"
        if self.spec.ex_events and ev.blocked(self.events_df, pos.symbol, ts, ts):
            return "event_blackout"
        return None

    def _try_index_entry(self, ts: pd.Timestamp) -> None:
        if C.INDEX in self.positions:
            return
        panel = self.nifty()
        row = row_at(panel, ts)
        if row is None or pd.isna(row.get("spot")) or pd.isna(row.get("atm_iv")):
            return
        expiries = self.src.expiries(C.INDEX)
        expiry = _next_tuesday(expiries, ts, C.MIN_DTE)
        if not expiry:
            self._skip(ts, C.INDEX, "no Tuesday expiry ≥8 DTE")
            return
        if self.spec.signal:
            rv = var.rv_nd_pct(self.daily(C.INDEX), ts)
            ok, why, gap = var.signal_ok(float(row["atm_iv"]), rv)
            if not ok:
                self._skip(ts, C.INDEX, why, vrp=gap)
                return
        else:
            gap = var.vrp_pts(float(row["atm_iv"]), var.rv_nd_pct(self.daily(C.INDEX), ts))
        self._open_straddle(ts, C.INDEX, expiry, "index", float(row["spot"]), float(row["atm_iv"]) / 100.0, gap)

    def _try_stock_entries(self, ts: pd.Timestamp) -> None:
        names = uni.tradeable_asof(ts, membership=self.membership)
        names = [s for s in names if s not in self.dead]
        live_n = max(1, len([s for s in names if s not in self.positions]))
        per = self.capital_budget / live_n
        for sym in names:
            if sym in self.positions:
                continue
            try:
                panel = self.src.panel(sym)
            except Exception as exc:
                self.dead.add(sym)
                self._skip(ts, sym, f"panel {exc}")
                continue
            if panel is None or panel.empty:
                self.dead.add(sym)
                self._skip(ts, sym, "empty panel")
                continue
            row = row_at(panel, ts)
            if row is None or pd.isna(row.get("spot")) or pd.isna(row.get("atm_iv")):
                self._skip(ts, sym, "no spot/IV")
                continue
            expiry = _next_monthly(self.src.expiries(sym), ts)
            if not expiry:
                self._skip(ts, sym, "no monthly expiry in DTE window")
                continue
            if self.spec.ex_events and ev.blocked(self.events_df, sym, ts, expiry):
                self._skip(ts, sym, "earnings/corporate blackout")
                continue
            gap = var.vrp_pts(float(row["atm_iv"]), var.rv_nd_pct(self.daily(sym), ts))
            if self.spec.signal:
                ok, why, gap = var.signal_ok(float(row["atm_iv"]), var.rv_nd_pct(self.daily(sym), ts))
                if not ok:
                    self._skip(ts, sym, why, vrp=gap)
                    continue
            self._open_straddle(
                ts, sym, expiry, "stock", float(row["spot"]), float(row["atm_iv"]) / 100.0, gap, capital=per
            )

    def _open_straddle(
        self,
        ts: pd.Timestamp,
        symbol: str,
        expiry: str,
        book: str,
        spot: float,
        iv: float,
        vrp: float,
        *,
        capital: float | None = None,
    ) -> None:
        t = years_to(ts, expiry)
        cmap = self.src.contracts(symbol, expiry)
        strikes = list(cmap) if cmap else None
        k = atm_forward_strike(spot, t, strikes=strikes, step=self.src.strike_step(symbol))
        lot = self.src.lot_size(symbol)
        n = lots_for_stress(
            spot, k, expiry, ts, iv, lot, hedge=self.spec.hedge, capital=capital or self.capital_budget
        )
        ce_sym = self.src.option_symbol(symbol, expiry, k, "call")
        pe_sym = self.src.option_symbol(symbol, expiry, k, "put")
        ce_row, pe_row = self._opt_rows(ce_sym, pe_sym, ts, expiry)
        ce_mid = ex.mid_from_ohlc(ce_row)
        pe_mid = ex.mid_from_ohlc(pe_row)
        if ce_mid is None or pe_mid is None or ce_sym is None or pe_sym is None:
            self._skip(ts, symbol, f"missing tape {expiry} K={k}")
            return
        ce_fill, src_c = ex.fill_price(ce_row, side="sell")
        pe_fill, src_p = ex.fill_price(pe_row, side="sell")
        if ce_fill is None or pe_fill is None:
            self._skip(ts, symbol, "no fill")
            return
        cash_mid = n * lot * (ce_mid + pe_mid)
        costs = ex.statutory_opt(n * lot * ce_mid, "sell")["total"] + ex.statutory_opt(n * lot * pe_mid, "sell")["total"]
        g0 = straddle_unit(spot, k, t, iv)
        fut = -g0["delta"] * n * lot if self.spec.hedge else 0.0
        if abs(fut) > 0:
            costs += ex.hedge_cost(spot * abs(fut), fut)
        roll = _roll_ts(ts, book, expiry, self.nifty())
        pos = Position(
            trade_id=f"{self.spec.id}-{symbol}-{ts.strftime('%Y%m%d%H')}-{expiry}",
            book=book,
            symbol=symbol,
            expiry=expiry,
            K=float(k),
            lots=int(n),
            lot=int(lot),
            ce_sym=ce_sym,
            pe_sym=pe_sym,
            entry_ts=ts,
            roll_ts=roll,
            ce_open_mid=float(ce_mid),
            pe_open_mid=float(pe_mid),
            ce_fill=float(ce_fill),
            pe_fill=float(pe_fill),
            fill_source=f"{src_c}/{src_p}",
            iv_entry=float(iv),
            spot_entry=float(spot),
            impl_var=var.implied_variance(iv, t),
            last_spot=float(spot),
            fut_units=float(fut),
            costs=float(costs),
            vrp=float(vrp) if vrp is not None else float("nan"),
            notes=f"ATM-F K={k:.2f} F={spot * np.exp(C.RISK_FREE * t):.2f} lots={n}",
        )
        self.positions[symbol] = pos
        m = margin_posted(spot, n, lot, fut, is_index=book == "index")
        self.risk_rows.append(
            dict(
                ts=str(ts),
                backtest=self.spec.id,
                symbol=symbol,
                expiry=expiry,
                lots=n,
                stress_capital=m["capital"],
                span=m["span"],
                fut_margin=m["fut"],
                premium_mid=cash_mid,
                vrp=pos.vrp,
                impl_var=pos.impl_var,
            )
        )
        print(
            f"  [{self.spec.id}] OPEN {symbol} {ts} {expiry} K={k:.1f} {n}x{lot} "
            f"mid {ce_mid+pe_mid:.2f} src {pos.fill_source} VRP {pos.vrp:.2f}"
        )

    def _close(self, symbol: str, ts: pd.Timestamp, reason: str) -> None:
        pos = self.positions.pop(symbol, None)
        if pos is None:
            return
        panel = self.src.panel(symbol if pos.book == "stock" else C.INDEX)
        row = row_at(panel, ts)
        spot = float(row["spot"]) if row is not None and pd.notna(row.get("spot")) else pos.last_spot
        iv = float(row["atm_iv"]) / 100.0 if row is not None and pd.notna(row.get("atm_iv")) else pos.iv_entry
        g = straddle_unit(spot, pos.K, years_to(ts, pos.expiry), iv)
        ce_row, pe_row = self._opt_rows(pos.ce_sym, pos.pe_sym, ts, pos.expiry)
        ce_mid = ex.mid_from_ohlc(ce_row) or g["ce"]
        pe_mid = ex.mid_from_ohlc(pe_row) or g["pe"]
        ce_fill, _ = ex.fill_price(pd.Series({"close": ce_mid}), side="buy")
        pe_fill, _ = ex.fill_price(pd.Series({"close": pe_mid}), side="buy")
        if ce_row is not None:
            ce_fill, _ = ex.fill_price(ce_row, side="buy")
        if pe_row is not None:
            pe_fill, _ = ex.fill_price(pe_row, side="buy")
        ce_fill = ce_fill or ce_mid
        pe_fill = pe_fill or pe_mid
        pos.costs += (
            ex.statutory_opt(pos.lots * pos.lot * ce_mid, "buy")["total"]
            + ex.statutory_opt(pos.lots * pos.lot * pe_mid, "buy")["total"]
        )
        if abs(pos.fut_units) > 0:
            pos.costs += ex.hedge_cost(spot * abs(pos.fut_units), -pos.fut_units)
            pos.fut_units = 0.0
        pnl_opt = pos.lots * pos.lot * ((pos.ce_fill + pos.pe_fill) - (ce_fill + pe_fill))
        pnl = pnl_opt + pos.pnl_fut - pos.costs
        self.closed.append(
            dict(
                trade_id=pos.trade_id,
                backtest=self.spec.id,
                book=pos.book,
                symbol=pos.symbol,
                expiry=pos.expiry,
                K=pos.K,
                lots=pos.lots,
                lot=pos.lot,
                entry_ts=str(pos.entry_ts),
                exit_ts=str(ts),
                exit_reason=reason,
                fill_source=pos.fill_source,
                ce_open_mid=pos.ce_open_mid,
                pe_open_mid=pos.pe_open_mid,
                ce_open_fill=pos.ce_fill,
                pe_open_fill=pos.pe_fill,
                ce_close_mid=ce_mid,
                pe_close_mid=pe_mid,
                straddle_open=pos.ce_fill + pos.pe_fill,
                straddle_close=ce_fill + pe_fill,
                pnl_opt=pnl_opt,
                pnl_fut=pos.pnl_fut,
                costs=pos.costs,
                pnl=pnl,
                vrp=pos.vrp,
                real_var=pos.real_var,
                impl_var=pos.impl_var,
                notes=pos.notes,
            )
        )
        print(f"  [{self.spec.id}] CLOSE {symbol} {ts} {reason} pnl {pnl:,.0f}")

    def _opt_rows(self, ce_sym, pe_sym, ts, expiry):
        start = (pd.Timestamp(ts) - pd.Timedelta(days=2)).to_pydatetime()
        end = (pd.Timestamp(expiry) + pd.Timedelta(days=1)).to_pydatetime()
        ce_df = self.src.option_ohlc(ce_sym, start, end) if ce_sym else None
        pe_df = self.src.option_ohlc(pe_sym, start, end) if pe_sym else None
        ce = ex.row_at_hour(ce_df, ts)
        pe = ex.row_at_hour(pe_df, ts)
        if ce is None:
            ce = ex.row_asof(ce_df, ts)
        if pe is None:
            pe = ex.row_asof(pe_df, ts)
        return ce, pe

    def _straddle_mark(self, pos: Position, ts: pd.Timestamp, bs_px: float) -> float:
        ce_row, pe_row = self._opt_rows(pos.ce_sym, pos.pe_sym, ts, pos.expiry)
        ce = ex.mid_from_ohlc(ce_row)
        pe = ex.mid_from_ohlc(pe_row)
        if ce is not None and pe is not None:
            return ce + pe
        return float(bs_px)

    def _skip(self, ts, symbol, reason, vrp=float("nan")):
        self.skips.append(dict(ts=str(ts), backtest=self.spec.id, symbol=symbol, reason=reason, vrp=vrp))

    def _frames(self) -> EngineResult:
        trades = pd.DataFrame(self.closed)
        hourly = pd.DataFrame(self.hourly_rows)
        risk = pd.DataFrame(self.risk_rows)
        skips = pd.DataFrame(self.skips)
        if hourly.empty:
            daily = pd.DataFrame()
        else:
            h = hourly.copy()
            h["ts"] = pd.to_datetime(h["ts"])
            h["date"] = h["ts"].dt.normalize()
            daily = (
                h.groupby(["date", "backtest", "book"], as_index=False)
                .agg(
                    pnl_opt_unreal=("pnl_opt_unreal", "last"),
                    pnl_fut=("pnl_fut", "last"),
                    costs=("costs", "last"),
                    n_names=("symbol", "nunique"),
                )
            )
        return EngineResult(trades=trades, hourly=hourly, daily=daily, risk=risk, skips=skips)


def _next_tuesday(expiries: list[str], ts: pd.Timestamp, min_dte: int) -> str | None:
    asof = pd.Timestamp(ts).normalize()
    live = []
    for e in sorted(set(expiries)):
        d = pd.Timestamp(e).normalize()
        if int(d.weekday()) != 1:
            continue
        if (d - asof).days < int(min_dte):
            continue
        live.append(e)
    return live[0] if live else None


def _next_monthly(expiries: list[str], ts: pd.Timestamp) -> str | None:
    asof = pd.Timestamp(ts).normalize()
    live = []
    for e in sorted(set(expiries)):
        if not is_monthly_expiry(e):
            continue
        dte = (pd.Timestamp(e).normalize() - asof).days
        if C.STOCK_MIN_DTE <= dte <= C.STOCK_MAX_DTE:
            live.append(e)
    return live[0] if live else None


def _roll_ts(entry: pd.Timestamp, book: str, expiry: str, nifty: pd.DataFrame) -> pd.Timestamp:
    if book == "index":
        target = pd.Timestamp(entry).normalize() + pd.Timedelta(days=7)
        target = target + pd.Timedelta(hours=C.ROLL_HOUR)
    else:
        dte_left = max((pd.Timestamp(expiry).normalize() - pd.Timestamp(entry).normalize()).days - C.STOCK_EXIT_DTE, 1)
        target = pd.Timestamp(entry).normalize() + pd.Timedelta(days=dte_left, hours=C.ROLL_HOUR)
    df = nifty.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    later = df[df["timestamp"] >= target]
    if later.empty:
        return pd.Timestamp(df["timestamp"].max())
    return pd.Timestamp(later["timestamp"].iloc[0])
