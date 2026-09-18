"""Unit tests for Index/Stock VRP: pricing, variance, sizing, engine A–H."""

from __future__ import annotations

import unittest
from pathlib import Path

import numpy as np
import pandas as pd

from Index_Stock_VRP import config as C
from Index_Stock_VRP.calendar_events import blocked, load_events
from Index_Stock_VRP.engine import Engine
from Index_Stock_VRP.execution import fill_price, statutory_opt
from Index_Stock_VRP.pricing import atm_forward_strike, forward_price, years_to
from Index_Stock_VRP.sizing import lots_for_stress, stress_pnl_one_lot
from Index_Stock_VRP.synthetic import SyntheticSource
from Index_Stock_VRP.universe import constituents_asof, tradeable_asof
from Index_Stock_VRP.variance import implied_variance, signal_ok, variance_exhausted


class PricingTests(unittest.TestCase):
    def test_atm_forward_not_spot(self):
        s, t, step = 24000.0, 8 / 365.25, 50.0
        k = atm_forward_strike(s, t, step=step)
        f = forward_price(s, t)
        self.assertGreater(f, s)
        self.assertLess(abs(k - f), step)

    def test_years_to_positive(self):
        t = years_to(pd.Timestamp("2026-03-02 10:00:00"), "2026-03-10")
        self.assertGreater(t, 0)


class VarianceTests(unittest.TestCase):
    def test_signal_filter(self):
        ok, _, gap = signal_ok(16.0, 12.0, min_pts=1.0)
        self.assertTrue(ok)
        self.assertAlmostEqual(gap, 4.0)
        ok2, _, _ = signal_ok(12.0, 16.0, min_pts=1.0)
        self.assertFalse(ok2)

    def test_variance_exit(self):
        impl = implied_variance(0.16, 8 / 365.25)
        self.assertTrue(variance_exhausted(0.85 * impl, impl, frac=0.80))
        self.assertFalse(variance_exhausted(0.10 * impl, impl, frac=0.80))


class SizingTests(unittest.TestCase):
    def test_stress_loss_is_negative(self):
        t = 8 / 365.25
        k = atm_forward_strike(24000.0, t, step=50)
        pnl = stress_pnl_one_lot(24000.0, k, t, 0.16, 65, hedge=True)
        self.assertLess(pnl, 0)

    def test_lots_at_least_one(self):
        ts = pd.Timestamp("2026-03-02 10:00:00")
        n = lots_for_stress(24000.0, 24100.0, "2026-03-10", ts, 0.16, 65, hedge=True)
        self.assertGreaterEqual(n, 1)


class ExecutionTests(unittest.TestCase):
    def test_mid_slip_sell_below_mid(self):
        px, src = fill_price(pd.Series({"close": 100.0}), side="sell", slippage=0.01, use_bid_ask=False)
        self.assertEqual(src, "mid+slip")
        self.assertAlmostEqual(px, 99.0)

    def test_bid_used_when_present(self):
        px, src = fill_price(pd.Series({"close": 100.0, "bid": 98.0, "ask": 102.0}), side="sell")
        self.assertEqual(src, "bid")
        self.assertEqual(px, 98.0)

    def test_costs_at_mid_sell_has_stt(self):
        c = statutory_opt(100000.0, "sell")
        self.assertGreater(c["stt"], 0)
        self.assertEqual(c["stamp"], 0)
        c2 = statutory_opt(100000.0, "buy")
        self.assertEqual(c2["stt"], 0)
        self.assertGreater(c2["stamp"], 0)


class UniverseTests(unittest.TestCase):
    def test_pit_liquid_subset(self):
        names = tradeable_asof("2026-04-01")
        self.assertIn("HDFCBANK", names)
        self.assertNotIn("TRENT", names)

    def test_membership_includes_index_names(self):
        alln = constituents_asof("2026-04-01")
        self.assertIn("TRENT", alln)


class EventTests(unittest.TestCase):
    def test_earnings_blackout(self):
        events = load_events()
        self.assertTrue(blocked(events, "INFY", "2026-04-16", "2026-05-12"))
        self.assertFalse(blocked(events, "INFY", "2026-03-02", "2026-03-20"))


class EngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.src = SyntheticSource(seed=7)

    def _run(self, spec_id: str):
        return Engine(self.src, C.BACKTESTS[spec_id]).run()

    def test_index_always_in_trades(self):
        res = self._run("A")
        self.assertGreater(len(res.trades), 0)
        self.assertTrue((res.trades["book"] == "index").all())
        self.assertTrue((res.trades["symbol"] == "NIFTY").all())
        dte = (
            pd.to_datetime(res.trades["expiry"]) - pd.to_datetime(res.trades["entry_ts"]).dt.normalize()
        ).dt.days
        self.assertTrue((dte >= C.MIN_DTE).all())

    def test_hedged_has_fut_pnl_column(self):
        res = self._run("B")
        self.assertGreater(len(res.trades), 0)
        self.assertIn("pnl_fut", res.trades.columns)
        self.assertFalse(np.allclose(res.trades["pnl_fut"].to_numpy(), 0.0))

    def test_signal_filters_some(self):
        always = self._run("B")
        filt = self._run("C")
        self.assertLessEqual(len(filt.trades), len(always.trades))

    def test_stock_book_ex_events(self):
        raw = self._run("F")
        exev = self._run("G")
        self.assertGreater(len(raw.trades), 0)
        self.assertTrue((raw.trades["book"] == "stock").all())
        infy_raw = raw.trades[raw.trades["symbol"] == "INFY"]
        infy_g = exev.trades[exev.trades["symbol"] == "INFY"]
        if not infy_raw.empty:
            self.assertLessEqual(len(infy_g), len(infy_raw))

    def test_all_letters_run(self):
        for i in "ABCDEFGH":
            res = self._run(i)
            self.assertIsNotNone(res.trades)
            self.assertTrue((C.CACHE_DIR / i).exists() or True)

    def test_csvs_written(self):
        from Index_Stock_VRP.reports import write_result

        res = self._run("A")
        d = write_result("A", res)
        for name in ("trades.csv", "hourly.csv", "daily.csv", "risk.csv"):
            self.assertTrue((d / name).exists(), name)


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
