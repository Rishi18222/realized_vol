"""Unit tests for the two-book daily-scan VRP engine."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from Index_Stock_VRP import config as C
from Index_Stock_VRP import schemas
from Index_Stock_VRP.calendar_events import blocked
from Index_Stock_VRP.engine import Engine
from Index_Stock_VRP.execution import fill_price, statutory_opt
from Index_Stock_VRP.pricing import atm_forward_strike, forward_price
from Index_Stock_VRP.sizing import lots_for_stress, stress_pnl_one_lot
from Index_Stock_VRP.synthetic import SyntheticSource
from Index_Stock_VRP.universe import constituents_asof, tradeable_asof
from Index_Stock_VRP.variance import (
    budget_exhausted,
    forecast_rv_ann,
    tenor_forecast_rv,
    trading_sessions_to_horizon,
    vrp_signal,
)


class ConfigTests(unittest.TestCase):
    def test_no_ah_ladder(self):
        self.assertEqual(C.FRAMEWORK_VERSION, 4)
        self.assertEqual(C.HEDGE_FREQUENCY, "1h")
        self.assertEqual(C.RV_WINDOWS, (5, 20, 60, 120))
        self.assertFalse(hasattr(C, "BACKTESTS"))
        self.assertNotIn("backtests", C.RAW)


class PricingTests(unittest.TestCase):
    def test_atm_forward_not_spot(self):
        s, t, step = 24000.0, 8 / 365.25, 50.0
        k = atm_forward_strike(s, t, step=step)
        f = forward_price(s, t)
        self.assertGreater(f, s)
        self.assertLess(abs(k - f), step)


class VarianceTests(unittest.TestCase):
    def test_forecast_renormalizes_missing_120(self):
        px = pd.Series(np.linspace(100, 110, 40), index=pd.bdate_range("2026-03-02", periods=40))
        rv, windows, wts = forecast_rv_ann(px, px.index[-1])
        self.assertTrue(np.isfinite(rv))
        self.assertNotIn(120, windows)
        self.assertNotIn(60, windows)
        self.assertIn(5, windows)
        self.assertAlmostEqual(sum(wts), 1.0, places=6)

    def test_ten_calendar_days_are_seven_sessions(self):
        n, src = trading_sessions_to_horizon([], "2026-04-01", "2026-04-11")
        self.assertEqual(n, 7)
        self.assertEqual(src, "calendar_5_7")

    def test_matched_lookback_is_remaining_sessions(self):
        px = pd.Series(np.linspace(100, 130, 80), index=pd.bdate_range("2026-01-02", periods=80))
        rv, windows, _, method = tenor_forecast_rv(px, px.index[-1], 7)
        self.assertTrue(np.isfinite(rv))
        self.assertEqual(windows[0], 7)
        self.assertIn("matched", method)

    def test_long_and_short(self):
        kw = dict(
            vega_1pct=50.0,
            lot=65,
            premium_1lot=30000.0,
            windows=[5],
            weights_used=[1.0],
            t_hold=21 / 252.0,
            t_opt=21 / 365.25,
            n_sessions=15,
            method="test",
        )
        rich = vrp_signal(0.22, 0.12, **kw)
        cheap = vrp_signal(0.10, 0.20, **kw)
        flat = vrp_signal(0.16, 0.159, **kw)
        self.assertEqual(rich.side, "short")
        self.assertEqual(cheap.side, "long")
        self.assertIsNone(flat.side)
        self.assertGreater(rich.implied_remaining_var, rich.expected_remaining_var)
        self.assertGreater(cheap.expected_remaining_var, cheap.implied_remaining_var)

    def test_tiny_near_expiry_long_is_skipped(self):
        sig = vrp_signal(
            0.16,
            0.1668,
            33.0,
            65,
            58500.0,
            [5],
            [1.0],
            t_hold=5 / 252.0,
            t_opt=11 / 365.25,
            n_sessions=5,
            method="matched",
        )
        self.assertIsNone(sig.side)
        self.assertGreater(sig.expected_remaining_var, sig.implied_remaining_var)

    def test_budget_full_not_80(self):
        self.assertTrue(budget_exhausted(1.0, 1.0))
        self.assertFalse(budget_exhausted(0.80, 1.0))


class SizingTests(unittest.TestCase):
    def test_short_stress_negative(self):
        t = 8 / 365.25
        k = atm_forward_strike(24000.0, t, step=50)
        pnl = stress_pnl_one_lot(24000.0, k, t, 0.16, 65, hedge=True, side="short")
        self.assertLess(pnl, 0)

    def test_long_stress_negative(self):
        t = 8 / 365.25
        k = atm_forward_strike(24000.0, t, step=50)
        pnl = stress_pnl_one_lot(24000.0, k, t, 0.16, 65, hedge=True, side="long")
        self.assertLess(pnl, 0)

    def test_lots_at_least_one(self):
        ts = pd.Timestamp("2026-03-02 10:00:00")
        n = lots_for_stress(24000.0, 24100.0, "2026-03-10", ts, 0.16, 65, hedge=True, side="short")
        self.assertGreaterEqual(n, 1)


class ExecutionTests(unittest.TestCase):
    def test_mid_slip_and_costs(self):
        px, src = fill_price(pd.Series({"close": 100.0}), side="sell", slippage=0.01, use_bid_ask=False)
        self.assertEqual(src, "mid+slip")
        self.assertAlmostEqual(px, 99.0)
        c = statutory_opt(100000.0, "sell")
        self.assertGreater(c["stt"], 0)


class UniverseTests(unittest.TestCase):
    def test_every_pit_name_not_liquid_filter(self):
        names = tradeable_asof("2026-04-01")
        self.assertIn("HDFCBANK", names)
        self.assertIn("TRENT", names)
        self.assertGreaterEqual(len(names), 40)
        self.assertIn("TRENT", constituents_asof("2026-04-01"))


class EventTests(unittest.TestCase):
    def test_event_in_life_not_tminus2(self):
        cols = ["symbol", "date", "event_type"]
        before = pd.DataFrame([("INFY", "2026-03-16", "earnings")], columns=cols)
        during = pd.DataFrame([("INFY", "2026-04-10", "earnings")], columns=cols)
        for df in (before, during):
            df["date"] = pd.to_datetime(df["date"])
        self.assertFalse(blocked(before, "INFY", "2026-03-17", "2026-04-16"))
        self.assertTrue(blocked(during, "INFY", "2026-03-17", "2026-04-16"))


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = SyntheticSource(seed=7)
        cls.res = Engine(cls.src).run()

    def test_one_run_two_books(self):
        self.assertFalse(self.res.trades.empty)
        books = set(self.res.trades["book"])
        self.assertIn("index", books)
        self.assertTrue((self.res.trades["hedge_frequency"] == "1h").all())
        self.assertTrue(self.res.trades["side"].isin(["long", "short"]).all())

    def test_index_hedge_is_nifty_proxy_stock_is_own(self):
        t = self.res.trades
        idx = t[t["book"] == "index"]
        stk = t[t["book"] == "stock"]
        if not idx.empty:
            self.assertTrue((idx["hedge_underlying"] == "spot_as_fut_proxy").all())
        if not stk.empty:
            self.assertFalse(stk["hedge_underlying"].str.contains("NIFTY").any())

    def test_remaining_var_on_trades(self):
        t = self.res.trades
        self.assertIn("implied_remaining_var", t.columns)
        self.assertIn("expected_remaining_var", t.columns)
        self.assertIn("n_sessions", t.columns)
        shorts = t[t["side"] == "short"]
        longs = t[t["side"] == "long"]
        if not shorts.empty:
            self.assertTrue((shorts["implied_remaining_var"] > shorts["expected_remaining_var"]).all())
        if not longs.empty:
            self.assertTrue((longs["expected_remaining_var"] > longs["implied_remaining_var"]).all())
        self.assertGreater(len(self.res.rejected), 0)
        made = set(self.res.trades["symbol"]) if not self.res.trades.empty else set()
        self.assertNotIn("TRENT", made)

    def test_output_schemas(self):
        from Index_Stock_VRP.reports import write_result

        with tempfile.TemporaryDirectory() as td:
            d = write_result(self.res, out_dir=Path(td))
            mapping = {
                "trade_log.csv": schemas.TRADE_LOG,
                "hourly_risk.csv": schemas.HOURLY_RISK,
                "hedge_log.csv": schemas.HEDGE_LOG,
                "rejected_signals.csv": schemas.REJECTED,
                "daily_performance.csv": schemas.DAILY,
            }
            for name, cols in mapping.items():
                self.assertTrue((d / name).exists(), name)
                header = Path(d / name).read_text().splitlines()[0].split(",")
                for c in cols:
                    self.assertIn(c, header, f"{name} missing {c}")
            self.assertFalse((d / "A").exists())
            self.assertFalse((d / "H").exists())
            self.assertTrue((d / "charts" / "equity.png").exists())


class StressTests(unittest.TestCase):
    def test_stress_module(self):
        from Index_Stock_VRP.stress import run_stress

        df = run_stress()
        self.assertTrue(bool(df["pass_"].all()), df.to_string(index=False))


class CacheOnlyImportTests(unittest.TestCase):
    def test_source_import_does_not_load_growwapi(self):
        import sys

        sys.modules.pop("growwapi", None)
        sys.modules.pop("Calendar_Dispersion_BT.groww_io", None)
        sys.modules.pop("underlying_vrp_pipeline", None)
        from Index_Stock_VRP import source as srcmod

        self.assertNotIn("growwapi", sys.modules)
        src = srcmod.GrowwSource(lookback_days=180, cache_only=True)
        panel = src.panel("NIFTY")
        self.assertFalse(panel.empty)
        self.assertNotIn("growwapi", sys.modules)


if __name__ == "__main__":
    unittest.main()
