"""Index VRP + Stock VRP rules. Two books, no dispersion."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = Path(__file__).resolve().parent
DATA_DIR = PKG_DIR / "data"
CACHE_DIR = PKG_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)
CHART_DIR = CACHE_DIR / "charts"
CHART_DIR.mkdir(exist_ok=True)

INDEX = "NIFTY"
RISK_FREE = 0.07
DIV_YIELD = 0.0
TRADING_DAYS = 252
TRADING_HOURS_PER_DAY = 6.25
LOOKBACK_DAYS = 180

# Index: Monday entry, short next-Tuesday ATM-forward weekly, min 8 DTE, roll next Monday.
ROLL_WEEKDAY = 0
ROLL_HOUR = 10
MIN_DTE = 8
FILL_HOURS = (10, 11, 12, 13, 14, 15)
HEDGE_OPEN_HOUR = 9
NIFTY_STRIKE_STEP = 50.0
NIFTY_LOT_FALLBACK = 65

# Stocks: monthly ATM straddles on liquid PIT Nifty constituents.
STOCK_MIN_DTE = 21
STOCK_MAX_DTE = 45
STOCK_EXIT_DTE = 7
EARNINGS_BLACKOUT_BEFORE = 2
EARNINGS_BLACKOUT_AFTER = 1

LIQUID_FNO = [
    "HDFCBANK",
    "RELIANCE",
    "ICICIBANK",
    "INFY",
    "ITC",
    "TCS",
    "BHARTIARTL",
    "LT",
    "SBIN",
    "AXISBANK",
    "KOTAKBANK",
    "BAJFINANCE",
]

DEFAULT_LOTS = {
    "NIFTY": 65,
    "HDFCBANK": 550,
    "RELIANCE": 500,
    "ICICIBANK": 700,
    "INFY": 400,
    "ITC": 1600,
    "TCS": 175,
    "BHARTIARTL": 475,
    "LT": 175,
    "SBIN": 750,
    "AXISBANK": 625,
    "KOTAKBANK": 400,
    "BAJFINANCE": 125,
}

DEFAULT_STEPS = {
    "NIFTY": 50.0,
    "HDFCBANK": 5.0,
    "RELIANCE": 10.0,
    "ICICIBANK": 5.0,
    "INFY": 5.0,
    "ITC": 2.5,
    "TCS": 20.0,
    "BHARTIARTL": 5.0,
    "LT": 20.0,
    "SBIN": 5.0,
    "AXISBANK": 5.0,
    "KOTAKBANK": 10.0,
    "BAJFINANCE": 20.0,
}

# Execution: bid/ask when present; otherwise mid ± explicit slippage. Statutory costs at mid.
SLIPPAGE_FRAC = 0.005
USE_BID_ASK = True

# Stress-loss sizing vs posted capital.
TARGET_CAPITAL = 2_500_000.0
STRESS_FRAC = 0.20
EM_MULT = 1.75
MARGIN_SHORT_PCT = 0.10
MARGIN_FUT_PCT = 0.11
MARGIN_STOCK_PCT = 0.20

# Variance signal / exit.
VRP_MIN_PTS = 1.0
VAR_EXIT_FRAC = 0.80
RV_LOOKBACK_DAYS = 5

FUT_STT_SELL = 0.0002
FUT_STAMP_BUY = 0.00002


@dataclass(frozen=True)
class BacktestSpec:
    id: str
    book: str
    hedge: bool
    signal: bool
    var_exit: bool
    ex_events: bool
    title: str


BACKTESTS: dict[str, BacktestSpec] = {
    "A": BacktestSpec("A", "index", False, False, False, False, "Index weekly, unhedged, always-in"),
    "B": BacktestSpec("B", "index", True, False, False, False, "Index weekly, delta-hedged, always-in"),
    "C": BacktestSpec("C", "index", True, True, False, False, "Index weekly, hedged, VRP filter"),
    "D": BacktestSpec("D", "index", True, True, True, False, "Index weekly, hedged, VRP + variance exit"),
    "E": BacktestSpec("E", "stock", False, False, False, False, "Stock monthly, unhedged, always-in"),
    "F": BacktestSpec("F", "stock", True, False, False, False, "Stock monthly, delta-hedged, always-in"),
    "G": BacktestSpec("G", "stock", True, False, False, True, "Stock monthly, hedged, ex-earnings"),
    "H": BacktestSpec("H", "stock", True, True, True, True, "Stock monthly, hedged, VRP + var exit, ex-events"),
}
