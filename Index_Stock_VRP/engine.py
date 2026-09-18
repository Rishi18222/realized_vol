"""One two-book VRP engine: daily scan, long or short vol, no A–H ladder."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import calendar_events as ev
from . import config as C
from . import execution as ex
from . import schemas
from . import universe as uni
from . import variance as var
from .pricing import atm_forward_strike, dte_days, expected_move, straddle_unit, years_to
from .sizing import lots_for_stress, stress_pnl_one_lot
from .source import is_monthly_expiry, row_at
from .span_elm import margin_straddle


@dataclass
class Position:
    trade_id: str
    book: str
    symbol: str
    side: str
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
    t_entry: float
    sold_var: float
    rv_forecast: float
    vrp_var: float
    vrp_pts: float
    rv_windows: str
    hedge_underlying: str
    n_sessions: int = 0
    t_hold: float = float("nan")
    implied_remaining_var: float = float("nan")
    expected_remaining_var: float = float("nan")
    net_edge: float = float("nan")
    rv_method: str = ""
    path_real_var: float = 0.0
    last_spot: float = 0.0
    fut_units: float = 0.0
    pnl_hedge: float = 0.0
    costs: float = 0.0
    span: float = 0.0
    elm: float = 0.0
    posted_margin: float = 0.0
    notes: str = ""

    @property
    def sign(self) -> float:
        return 1.0 if self.side == "long" else -1.0


@dataclass
class EngineResult:
    trades: pd.DataFrame
    hourly: pd.DataFrame
    daily: pd.DataFrame
    hedges: pd.DataFrame
    rejected: pd.DataFrame


class Engine:
    def __init__(
        self,
        src,
        *,
        events_df: pd.DataFrame | None = None,
        membership: pd.DataFrame | None = None,
        capital: float = C.TARGET_CAPITAL,
    ):
        self.src = src
        self.events_df = events_df if events_df is not None else ev.load_events()
        self.membership = membership if membership is not None else uni.load_membership()
        self.capital_budget = float(capital)
        self.positions: dict[str, Position] = {}
        self.closed: list[dict] = []
        self.hourly_rows: list[dict] = []
        self.hedge_rows: list[dict] = []
        self.rejected: list[dict] = []
        self.dead: set[str] = set()
        self._nifty: pd.DataFrame | None = None
        self._daily: dict[str, pd.Series] = {}
        self._sessions: pd.DatetimeIndex | None = None

    def nifty(self) -> pd.DataFrame:
        if self._nifty is None:
            self._nifty = self.src.panel(C.INDEX)
        return self._nifty

    def session_days(self) -> pd.DatetimeIndex:
        if self._sessions is None:
            self._sessions = var.session_days_from_panel(self.nifty())
        return self._sessions

    def daily_px(self, symbol: str, panel: pd.DataFrame) -> pd.Series:
        if symbol not in self._daily:
            self._daily[symbol] = var.daily_close_from_hourly(var.hourly_spot(panel))
        return self._daily[symbol]

    def run(self) -> EngineResult:
        panel = self.nifty()
        ts_all = sorted(pd.to_datetime(panel["timestamp"]).unique())
        print(
            f"[VRP] two-book daily scan  bars={len(ts_all)}  "
            f"hedge={C.HEDGE_FREQUENCY}  scan_hour={C.SCAN_HOUR}"
        )
        for ts in ts_all:
            ts = pd.Timestamp(ts)
            self._on_bar(ts)
            if int(ts.hour) != C.SCAN_HOUR:
                continue
            if C.INDEX not in self.positions:
                self._scan_index(ts)
            names = [s for s in uni.constituents_asof(ts, membership=self.membership) if s != C.INDEX]
            n_stock = max(len(names), 1)
            per = self.capital_budget / n_stock
            for sym in names:
                if sym in self.positions or sym in self.dead:
                    continue
                self._scan_stock(ts, sym, capital=per)
        for sym in list(self.positions):
            ts = pd.Timestamp(self.nifty()["timestamp"].max())
            self._close(sym, ts, "eod_flatten")
        return self._frames()

    def _on_bar(self, ts: pd.Timestamp) -> None:
        for sym in list(self.positions):
            pos = self.positions[sym]
            try:
                panel = self.src.panel(sym if pos.book == "stock" else C.INDEX)
            except Exception:
                continue
            row = row_at(panel, ts)
            if row is None or pd.isna(row.get("spot")):
                continue
            spot = float(row["spot"])
            iv = float(row["atm_iv"]) / 100.0 if pd.notna(row.get("atm_iv")) else pos.iv_entry
            if pos.last_spot > 0 and spot > 0:
                pos.path_real_var += float(np.log(spot / pos.last_spot) ** 2)
                pos.pnl_hedge += pos.fut_units * (spot - pos.last_spot)
            pos.last_spot = spot
            t_now = years_to(ts, pos.expiry)
            g = straddle_unit(spot, pos.K, t_now, iv)
            if int(ts.hour) >= C.HEDGE_OPEN_HOUR:
                target = -g["delta"] * pos.sign * pos.lots * pos.lot
                d_u = target - pos.fut_units
                if abs(d_u) > 1e-6:
                    cost = ex.hedge_cost(spot * abs(d_u), d_u)
                    pos.costs += cost
                    pos.fut_units = target
                    self.hedge_rows.append(
                        dict(
                            ts=str(ts),
                            book=pos.book,
                            symbol=pos.symbol,
                            side=pos.side,
                            hedge_underlying=pos.hedge_underlying,
                            hedge_frequency=C.HEDGE_FREQUENCY,
                            d_units=d_u,
                            units_after=pos.fut_units,
                            spot=spot,
                            cost=cost,
                            reason="rehedge",
                        )
                    )
            mark = self._straddle_mark(pos, ts, g["price"])
            opt_unreal = pos.sign * pos.lots * pos.lot * (mark - (pos.ce_fill + pos.pe_fill))
            elapsed = max((pd.Timestamp(ts) - pos.entry_ts).total_seconds() / (365.25 * 24 * 3600), 0.0)
            hot = var.running_hot_ratio(pos.path_real_var, elapsed, pos.sold_var, pos.t_entry)
            self.hourly_rows.append(
                dict(
                    ts=str(ts),
                    book=pos.book,
                    symbol=pos.symbol,
                    side=pos.side,
                    expiry=pos.expiry,
                    K=pos.K,
                    spot=spot,
                    iv=iv * 100.0,
                    straddle_mark=mark,
                    hedge_units=pos.fut_units,
                    hedge_frequency=C.HEDGE_FREQUENCY,
                    hedge_underlying=pos.hedge_underlying,
                    delta=g["delta"] * pos.sign,
                    gamma=g["gamma"],
                    vega=g["vega"] * pos.sign,
                    theta=g["theta"] * pos.sign,
                    path_real_var=pos.path_real_var,
                    sold_var=pos.sold_var,
                    remaining_var=pos.sold_var - pos.path_real_var,
                    running_hot_ratio=hot,
                    pnl_opt_unreal=opt_unreal,
                    pnl_hedge=pos.pnl_hedge,
                    costs=pos.costs,
                    span=pos.span,
                    elm=pos.elm,
                    posted_margin=pos.posted_margin,
                )
            )
            why = self._exit_reason(pos, ts, spot, iv, t_now, elapsed)
            if why:
                self._close(sym, ts, why)

    def _exit_reason(self, pos: Position, ts: pd.Timestamp, spot: float, iv: float, t_now: float, elapsed: float) -> str | None:
        if ts >= pos.roll_ts and int(ts.hour) >= C.SCAN_HOUR:
            return "weekly_roll" if pos.book == "index" else "monthly_roll"
        if pos.book == "stock" and dte_days(ts, pos.expiry) <= C.STOCK_EXIT_DTE and int(ts.hour) >= C.SCAN_HOUR:
            return "dte_exit"
        if pos.side == "short":
            if var.budget_exhausted(pos.path_real_var, pos.sold_var):
                return "variance_budget"
            if var.is_running_hot(pos.path_real_var, elapsed, pos.sold_var, pos.t_entry):
                return "running_hot"
            if var.crush_take(iv, t_now, pos.sold_var, pos.path_real_var):
                return "iv_crush"
            em = expected_move(pos.spot_entry, pos.iv_entry, max(dte_days(ts, pos.expiry), 1))
            if em > 0 and abs(spot - pos.spot_entry) >= C.EM_MULT * em and ts < pos.roll_ts:
                return "em_stress"
        else:
            if var.budget_exhausted(pos.path_real_var, pos.sold_var):
                return "variance_harvest"
            if var.crush_take(iv, t_now, pos.sold_var, pos.path_real_var):
                return "iv_crush_stop"
        return None

    def _scan_index(self, ts: pd.Timestamp) -> None:
        panel = self.nifty()
        row = row_at(panel, ts)
        if row is None or pd.isna(row.get("spot")) or pd.isna(row.get("atm_iv")):
            self._reject(ts, "index", C.INDEX, "no spot/IV")
            return
        expiry = _next_tuesday(self.src.expiries(C.INDEX), ts, C.MIN_DTE)
        if not expiry:
            self._reject(ts, "index", C.INDEX, "no Tuesday expiry ≥8 DTE")
            return
        self._try_open(ts, C.INDEX, expiry, "index", row, capital=self.capital_budget)

    def _scan_stock(self, ts: pd.Timestamp, sym: str, *, capital: float) -> None:
        try:
            panel = self.src.panel(sym)
        except Exception as exc:
            self.dead.add(sym)
            self._reject(ts, "stock", sym, f"no ATM-IV cache ({exc.__class__.__name__})")
            return
        if panel is None or panel.empty:
            self.dead.add(sym)
            self._reject(ts, "stock", sym, "empty ATM-IV panel")
            return
        row = row_at(panel, ts)
        if row is None or pd.isna(row.get("spot")) or pd.isna(row.get("atm_iv")):
            self._reject(ts, "stock", sym, "no spot/IV")
            return
        expiry = _next_monthly(self.src.expiries(sym), ts)
        if not expiry:
            self._reject(ts, "stock", sym, "no monthly expiry in DTE window")
            return
        if ev.blocked(self.events_df, sym, ts, expiry):
            self._reject(ts, "stock", sym, "event in option life [entry, expiry]")
            return
        self._try_open(ts, sym, expiry, "stock", row, capital=capital)

    def _try_open(self, ts, symbol, expiry, book, row, *, capital: float) -> None:
        iv = float(row["atm_iv"]) / 100.0
        spot = float(row["spot"])
        t_opt = years_to(ts, expiry)
        horizon = var.trade_horizon(ts, book, expiry)
        n_sess, sess_src = var.trading_sessions_to_horizon(self.session_days(), ts, horizon)
        t_hold = var.remaining_t_years(n_sess)
        try:
            panel = self.src.panel(symbol if book == "stock" else C.INDEX)
        except Exception as exc:
            self._reject(ts, book, symbol, f"panel {exc}")
            return
        daily = self.daily_px(symbol, panel)
        rv_f, windows, wts, method = var.tenor_forecast_rv(daily, ts, n_sess)
        method = f"{method}|{sess_src}"
        cmap = self.src.contracts(symbol, expiry)
        if not cmap:
            self._reject(ts, book, symbol, "no option tape", iv=iv, rv=rv_f, windows=windows)
            return
        k = atm_forward_strike(spot, t_opt, strikes=list(cmap), step=self.src.strike_step(symbol))
        lot = self.src.lot_size(symbol)
        g0 = straddle_unit(spot, k, t_opt, iv)
        ce_sym = self.src.option_symbol(symbol, expiry, k, "call")
        pe_sym = self.src.option_symbol(symbol, expiry, k, "put")
        ce_row, pe_row = self._opt_rows(ce_sym, pe_sym, ts, expiry)
        ce_mid = ex.mid_from_ohlc(ce_row)
        pe_mid = ex.mid_from_ohlc(pe_row)
        if ce_mid is None or pe_mid is None or ce_sym is None or pe_sym is None:
            self._reject(
                ts, book, symbol, f"no option tape {expiry} K={k}", iv=iv, rv=rv_f, windows=windows
            )
            return
        prem_1 = lot * (ce_mid + pe_mid)
        sig = var.vrp_signal(
            iv,
            rv_f,
            g0["vega"],
            lot,
            prem_1,
            windows,
            wts,
            t_hold=t_hold,
            t_opt=t_opt,
            n_sessions=n_sess,
            method=method,
        )
        if sig.side is None:
            would = None
            if np.isfinite(sig.vrp_pts):
                if sig.vrp_pts > 0:
                    would = "short"
                elif sig.vrp_pts < 0:
                    would = "long"
            self._reject(
                ts,
                book,
                symbol,
                sig.reason,
                iv=iv,
                rv=rv_f,
                windows=windows,
                vrp_var=sig.vrp_var,
                vrp_pts=sig.vrp_pts,
                net=sig.net_1lot,
                would=would,
                implied_remaining_var=sig.implied_remaining_var,
                expected_remaining_var=sig.expected_remaining_var,
                n_sessions=n_sess,
                t_hold=t_hold,
                rv_method=method,
            )
            return
        n = lots_for_stress(spot, k, expiry, ts, iv, lot, hedge=True, side=sig.side, capital=capital)
        open_side = "buy" if sig.side == "long" else "sell"
        ce_fill, src_c = ex.fill_price(ce_row, side=open_side)
        pe_fill, src_p = ex.fill_price(pe_row, side=open_side)
        if ce_fill is None or pe_fill is None:
            self._reject(ts, book, symbol, "no fill", iv=iv, rv=rv_f, windows=windows)
            return
        costs = (
            ex.statutory_opt(n * lot * ce_mid, open_side)["total"]
            + ex.statutory_opt(n * lot * pe_mid, open_side)["total"]
        )
        sign = 1.0 if sig.side == "long" else -1.0
        fut = -g0["delta"] * sign * n * lot
        if abs(fut) > 0:
            costs += ex.hedge_cost(spot * abs(fut), fut)
        hedge_und = C.HEDGE_UNDERLYING if book == "index" else f"{symbol}_spot_proxy"
        roll = _roll_ts(ts, book, expiry, self.nifty())
        sold = var.sold_variance(iv, t_opt)
        pos = Position(
            trade_id=f"{book}-{sig.side}-{symbol}-{ts.strftime('%Y%m%d%H')}-{expiry}",
            book=book,
            symbol=symbol,
            side=sig.side,
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
            t_entry=float(t_opt),
            sold_var=float(sold),
            rv_forecast=float(rv_f) if np.isfinite(rv_f) else float("nan"),
            vrp_var=float(sig.vrp_var),
            vrp_pts=float(sig.vrp_pts),
            rv_windows=",".join(str(x) for x in windows),
            hedge_underlying=hedge_und,
            n_sessions=int(n_sess),
            t_hold=float(t_hold),
            implied_remaining_var=float(sig.implied_remaining_var),
            expected_remaining_var=float(sig.expected_remaining_var),
            net_edge=float(sig.net_1lot) * int(n),
            rv_method=method,
            last_spot=float(spot),
            fut_units=float(fut),
            costs=float(costs),
            notes=(
                f"ATM-F K={k:.2f} {sig.side} lots={n} hedge={C.HEDGE_FREQUENCY}/{hedge_und} "
                f"n={n_sess} T={t_hold:.5f} method={method} "
                f"implVar={sig.implied_remaining_var:.6g} expVar={sig.expected_remaining_var:.6g}"
            ),
        )
        m = margin_straddle(
            symbol, expiry, k, n, lot, spot, iv, ts, fut, is_index=book == "index", book_side=sig.side
        )
        pos.span, pos.elm, pos.posted_margin = m.span, m.elm, m.posted
        self.positions[symbol] = pos
        self.hedge_rows.append(
            dict(
                ts=str(ts),
                book=book,
                symbol=symbol,
                side=sig.side,
                hedge_underlying=hedge_und,
                hedge_frequency=C.HEDGE_FREQUENCY,
                d_units=fut,
                units_after=fut,
                spot=spot,
                cost=ex.hedge_cost(spot * abs(fut), fut) if abs(fut) else 0.0,
                reason="entry",
            )
        )
        print(
            f"  OPEN {sig.side:5} {symbol} {ts} {expiry} K={k:.1f} {n}x{lot} "
            f"n={n_sess} remVRP {sig.vrp_var:.3g} src {pos.fill_source}"
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
        close_side = "sell" if pos.side == "long" else "buy"
        ce_fill, _ = ex.fill_price(pd.Series({"close": ce_mid}), side=close_side)
        pe_fill, _ = ex.fill_price(pd.Series({"close": pe_mid}), side=close_side)
        if ce_row is not None:
            ce_fill, _ = ex.fill_price(ce_row, side=close_side)
        if pe_row is not None:
            pe_fill, _ = ex.fill_price(pe_row, side=close_side)
        ce_fill = ce_fill or ce_mid
        pe_fill = pe_fill or pe_mid
        pos.costs += (
            ex.statutory_opt(pos.lots * pos.lot * ce_mid, close_side)["total"]
            + ex.statutory_opt(pos.lots * pos.lot * pe_mid, close_side)["total"]
        )
        if abs(pos.fut_units) > 0:
            pos.costs += ex.hedge_cost(spot * abs(pos.fut_units), -pos.fut_units)
            self.hedge_rows.append(
                dict(
                    ts=str(ts),
                    book=pos.book,
                    symbol=pos.symbol,
                    side=pos.side,
                    hedge_underlying=pos.hedge_underlying,
                    hedge_frequency=C.HEDGE_FREQUENCY,
                    d_units=-pos.fut_units,
                    units_after=0.0,
                    spot=spot,
                    cost=ex.hedge_cost(spot * abs(pos.fut_units), -pos.fut_units),
                    reason="flatten",
                )
            )
            pos.fut_units = 0.0
        open_px = pos.ce_fill + pos.pe_fill
        close_px = ce_fill + pe_fill
        pnl_opt = pos.sign * pos.lots * pos.lot * (close_px - open_px)
        pnl = pnl_opt + pos.pnl_hedge - pos.costs
        self.closed.append(
            dict(
                trade_id=pos.trade_id,
                book=pos.book,
                symbol=pos.symbol,
                side=pos.side,
                expiry=pos.expiry,
                K=pos.K,
                lots=pos.lots,
                lot=pos.lot,
                entry_ts=str(pos.entry_ts),
                exit_ts=str(ts),
                exit_reason=reason,
                dte_entry=dte_days(pos.entry_ts, pos.expiry),
                fill_source=pos.fill_source,
                hedge_frequency=C.HEDGE_FREQUENCY,
                hedge_underlying=pos.hedge_underlying,
                ce_sym=pos.ce_sym,
                pe_sym=pos.pe_sym,
                ce_open_mid=pos.ce_open_mid,
                pe_open_mid=pos.pe_open_mid,
                ce_open_fill=pos.ce_fill,
                pe_open_fill=pos.pe_fill,
                ce_close_mid=ce_mid,
                pe_close_mid=pe_mid,
                straddle_open=open_px,
                straddle_close=close_px,
                pnl_opt=pnl_opt,
                pnl_hedge=pos.pnl_hedge,
                costs=pos.costs,
                pnl=pnl,
                iv_entry=pos.iv_entry,
                rv_forecast=pos.rv_forecast,
                vrp_var=pos.vrp_var,
                vrp_pts=pos.vrp_pts,
                rv_windows=pos.rv_windows,
                n_sessions=pos.n_sessions,
                t_hold=pos.t_hold,
                implied_remaining_var=pos.implied_remaining_var,
                expected_remaining_var=pos.expected_remaining_var,
                net_edge=pos.net_edge,
                rv_method=pos.rv_method,
                sold_var=pos.sold_var,
                path_real_var=pos.path_real_var,
                remaining_var=pos.sold_var - pos.path_real_var,
                notes=pos.notes,
            )
        )
        print(f"  CLOSE {pos.side:5} {symbol} {ts} {reason} pnl {pnl:,.0f}")

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

    def _reject(
        self,
        ts,
        book,
        symbol,
        reason,
        iv=float("nan"),
        rv=float("nan"),
        windows=None,
        vrp_var=float("nan"),
        vrp_pts=float("nan"),
        net=float("nan"),
        would=None,
        implied_remaining_var=float("nan"),
        expected_remaining_var=float("nan"),
        n_sessions=float("nan"),
        t_hold=float("nan"),
        rv_method="",
    ):
        self.rejected.append(
            dict(
                ts=str(ts),
                book=book,
                symbol=symbol,
                reason=reason,
                iv=iv,
                rv_forecast=rv,
                vrp_var=vrp_var,
                vrp_pts=vrp_pts,
                net_edge=net,
                rv_windows=",".join(str(x) for x in (windows or [])),
                would_side=would or "",
                implied_remaining_var=implied_remaining_var,
                expected_remaining_var=expected_remaining_var,
                n_sessions=n_sessions,
                t_hold=t_hold,
                rv_method=rv_method,
            )
        )

    def _frames(self) -> EngineResult:
        trades = schemas.conform(pd.DataFrame(self.closed), schemas.TRADE_LOG)
        hourly = schemas.conform(pd.DataFrame(self.hourly_rows), schemas.HOURLY_RISK)
        hedges = schemas.conform(pd.DataFrame(self.hedge_rows), schemas.HEDGE_LOG)
        rejected = schemas.conform(pd.DataFrame(self.rejected), schemas.REJECTED)
        if hourly.empty:
            daily = schemas.conform(pd.DataFrame(), schemas.DAILY)
        else:
            h = hourly.copy()
            h["ts"] = pd.to_datetime(h["ts"])
            h["date"] = h["ts"].dt.normalize()
            last = h.sort_values("ts").groupby(["date", "book", "symbol"], as_index=False).last()
            g = last.groupby("date", as_index=False).agg(
                n_index_open=("book", lambda s: int((s == "index").sum())),
                n_stock_open=("book", lambda s: int((s == "stock").sum())),
                pnl_opt=("pnl_opt_unreal", "sum"),
                pnl_hedge=("pnl_hedge", "sum"),
                costs=("costs", "sum"),
                span=("span", "sum"),
                elm=("elm", "sum"),
                posted_margin=("posted_margin", "sum"),
            )
            idx = last[last["book"] == "index"].groupby("date")["pnl_opt_unreal"].sum()
            stk = last[last["book"] == "stock"].groupby("date")["pnl_opt_unreal"].sum()
            g["pnl_index"] = g["date"].map(idx).fillna(0.0)
            g["pnl_stock"] = g["date"].map(stk).fillna(0.0)
            g["pnl"] = g["pnl_opt"] + g["pnl_hedge"] - g["costs"]
            g = g.sort_values("date")
            g["equity"] = g["pnl"].cumsum()
            g["drawdown"] = g["equity"] - g["equity"].cummax()
            daily = schemas.conform(g, schemas.DAILY)
        return EngineResult(trades=trades, hourly=hourly, daily=daily, hedges=hedges, rejected=rejected)


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
        target = pd.Timestamp(entry).normalize() + pd.Timedelta(days=7, hours=C.SCAN_HOUR)
    else:
        dte_left = max((pd.Timestamp(expiry).normalize() - pd.Timestamp(entry).normalize()).days - C.STOCK_EXIT_DTE, 1)
        target = pd.Timestamp(entry).normalize() + pd.Timedelta(days=dte_left, hours=C.SCAN_HOUR)
    df = nifty.copy()
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    later = df[df["timestamp"] >= target]
    if later.empty:
        return pd.Timestamp(df["timestamp"].max())
    return pd.Timestamp(later["timestamp"].iloc[0])
