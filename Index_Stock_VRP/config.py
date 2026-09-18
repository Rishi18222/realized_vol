"""Index VRP + Stock VRP rules. Loaded from JSON (YAML if PyYAML is installed)."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = Path(__file__).resolve().parent
DATA_DIR = PKG_DIR / "data"
CACHE_DIR = PKG_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)
CHART_DIR = CACHE_DIR / "charts"
CHART_DIR.mkdir(exist_ok=True)
CONFIGS_DIR = PKG_DIR / "configs"
DEFAULT_CONFIG = CONFIGS_DIR / "default.json"

FRAMEWORK_VERSION = 2
HEDGE_FREQUENCY = "1h"
HEDGE_UNDERLYING = "spot_as_fut_proxy"
INDEX = "NIFTY"
RISK_FREE = 0.07
DIV_YIELD = 0.0
TRADING_DAYS = 252
NATIVE_BARS_PER_DAY = 7
NATIVE_HOURS = (9, 10, 11, 12, 13, 14, 15)
LOOKBACK_DAYS = 180
TARGET_CAPITAL = 2_500_000.0

ROLL_WEEKDAY = 0
ROLL_HOUR = 10
MIN_DTE = 8
FILL_HOURS = (10, 11, 12, 13, 14, 15)
HEDGE_OPEN_HOUR = 9
NIFTY_STRIKE_STEP = 50.0
NIFTY_LOT_FALLBACK = 65

STOCK_MIN_DTE = 21
STOCK_MAX_DTE = 45
STOCK_EXIT_DTE = 7

LIQUID_FNO: list[str] = []
DEFAULT_LOTS: dict[str, int] = {}
DEFAULT_STEPS: dict[str, float] = {}

SLIPPAGE_FRAC = 0.005
USE_BID_ASK = True

STRESS_FRAC = 0.20
EM_MULT = 1.75
MAX_LOTS = 200
MARGIN_SHORT_PCT = 0.10
MARGIN_FUT_PCT = 0.11
MARGIN_STOCK_PCT = 0.20
ELM_INDEX = 0.02
ELM_STOCK = 0.035
SPAN_SHORT_PCT_INDEX = 0.10
SPAN_SHORT_PCT_STOCK = 0.20

VAR_RATIO_MIN = 1.0
Z_MIN = 0.5
Z_LOOKBACK_OBS = 40
Z_MIN_OBS = 12
CRUSH_FRAC = 0.30
RUNNING_HOT_MULT = 2.0
RUNNING_HOT_MIN_HOURS = 7
EVENTS_MODE = "event_in_life"

STT_OPT_SELL = 0.0015
STAMP_OPT_BUY = 0.00003
NSE_OPT = 0.0003553
SEBI = 0.000001
GST = 0.18
FUT_STT_SELL = 0.0002
FUT_STAMP_BUY = 0.00002

RAW: dict = {}


@dataclass(frozen=True)
class BacktestSpec:
    id: str
    book: str
    hedge: bool
    signal: bool
    var_exit: bool
    ex_events: bool
    title: str


BACKTESTS: dict[str, BacktestSpec] = {}


def _parse(path: Path) -> dict:
    text = path.read_text()
    suffix = path.suffix.lower()
    if suffix in {".yaml", ".yml"}:
        try:
            import yaml  # type: ignore

            data = yaml.safe_load(text)
            if isinstance(data, dict):
                return data
        except ImportError:
            pass
        return json.loads(text)
    return json.loads(text)


def load_file(path: str | Path | None = None) -> dict:
    """Load YAML/JSON config into module-level constants."""
    global RAW, FRAMEWORK_VERSION, HEDGE_FREQUENCY, HEDGE_UNDERLYING, INDEX, RISK_FREE, DIV_YIELD
    global TRADING_DAYS, NATIVE_BARS_PER_DAY, NATIVE_HOURS, LOOKBACK_DAYS, TARGET_CAPITAL
    global ROLL_WEEKDAY, ROLL_HOUR, MIN_DTE, FILL_HOURS, HEDGE_OPEN_HOUR, NIFTY_STRIKE_STEP, NIFTY_LOT_FALLBACK
    global STOCK_MIN_DTE, STOCK_MAX_DTE, STOCK_EXIT_DTE, LIQUID_FNO, DEFAULT_LOTS, DEFAULT_STEPS
    global SLIPPAGE_FRAC, USE_BID_ASK, STRESS_FRAC, EM_MULT, MAX_LOTS
    global MARGIN_SHORT_PCT, MARGIN_FUT_PCT, MARGIN_STOCK_PCT, ELM_INDEX, ELM_STOCK
    global SPAN_SHORT_PCT_INDEX, SPAN_SHORT_PCT_STOCK
    global VAR_RATIO_MIN, Z_MIN, Z_LOOKBACK_OBS, Z_MIN_OBS, CRUSH_FRAC, RUNNING_HOT_MULT, RUNNING_HOT_MIN_HOURS, EVENTS_MODE
    global STT_OPT_SELL, STAMP_OPT_BUY, NSE_OPT, SEBI, GST, FUT_STT_SELL, FUT_STAMP_BUY, BACKTESTS

    p = Path(path) if path is not None else DEFAULT_CONFIG
    RAW = _parse(p)
    FRAMEWORK_VERSION = int(RAW.get("framework_version", 2))
    HEDGE_FREQUENCY = str(RAW.get("hedge_frequency", "1h"))
    HEDGE_UNDERLYING = str(RAW.get("hedge_underlying", "spot_as_fut_proxy"))
    INDEX = str(RAW.get("index", "NIFTY"))
    RISK_FREE = float(RAW.get("risk_free", 0.07))
    DIV_YIELD = float(RAW.get("div_yield", 0.0))
    TRADING_DAYS = int(RAW.get("trading_days", 252))
    NATIVE_BARS_PER_DAY = int(RAW.get("native_bars_per_day", 7))
    NATIVE_HOURS = tuple(int(h) for h in RAW.get("native_hours", [9, 10, 11, 12, 13, 14, 15]))
    LOOKBACK_DAYS = int(RAW.get("lookback_days", 180))
    TARGET_CAPITAL = float(RAW.get("target_capital", 2_500_000.0))

    ib = RAW.get("books", {}).get("index", {})
    sb = RAW.get("books", {}).get("stock", {})
    ROLL_WEEKDAY = int(ib.get("roll_weekday", 0))
    ROLL_HOUR = int(ib.get("roll_hour", 10))
    MIN_DTE = int(ib.get("min_dte", 8))
    FILL_HOURS = tuple(int(h) for h in ib.get("fill_hours", [10, 11, 12, 13, 14, 15]))
    HEDGE_OPEN_HOUR = int(ib.get("hedge_open_hour", 9))
    NIFTY_STRIKE_STEP = float(ib.get("strike_step", 50.0))
    NIFTY_LOT_FALLBACK = int(ib.get("lot_fallback", 65))
    STOCK_MIN_DTE = int(sb.get("min_dte", 21))
    STOCK_MAX_DTE = int(sb.get("max_dte", 45))
    STOCK_EXIT_DTE = int(sb.get("exit_dte", 7))

    LIQUID_FNO = [str(s).upper() for s in RAW.get("liquid_fno", [])]
    DEFAULT_LOTS = {str(k).upper(): int(v) for k, v in RAW.get("default_lots", {}).items()}
    DEFAULT_STEPS = {str(k).upper(): float(v) for k, v in RAW.get("default_steps", {}).items()}

    ex = RAW.get("execution", {})
    SLIPPAGE_FRAC = float(ex.get("slippage_frac", 0.005))
    USE_BID_ASK = bool(ex.get("use_bid_ask", True))

    sz = RAW.get("sizing", {})
    STRESS_FRAC = float(sz.get("stress_frac", 0.20))
    EM_MULT = float(sz.get("em_mult", RAW.get("exits", {}).get("em_mult", 1.75)))
    MAX_LOTS = int(sz.get("max_lots", 200))

    mg = RAW.get("margins", {})
    ELM_INDEX = float(mg.get("elm_index", 0.02))
    ELM_STOCK = float(mg.get("elm_stock", 0.035))
    SPAN_SHORT_PCT_INDEX = float(mg.get("span_short_pct_index", 0.10))
    SPAN_SHORT_PCT_STOCK = float(mg.get("span_short_pct_stock", 0.20))
    MARGIN_SHORT_PCT = SPAN_SHORT_PCT_INDEX
    MARGIN_FUT_PCT = float(mg.get("fut_pct_index", 0.11))
    MARGIN_STOCK_PCT = float(mg.get("fut_pct_stock", SPAN_SHORT_PCT_STOCK))

    sig = RAW.get("signal", {})
    VAR_RATIO_MIN = float(sig.get("var_ratio_min", 1.0))
    Z_MIN = float(sig.get("z_min", 0.5))
    Z_LOOKBACK_OBS = int(sig.get("z_lookback_obs", 40))
    Z_MIN_OBS = int(sig.get("z_min_obs", 12))

    xt = RAW.get("exits", {})
    CRUSH_FRAC = float(xt.get("crush_frac", 0.30))
    RUNNING_HOT_MULT = float(xt.get("running_hot_mult", 2.0))
    RUNNING_HOT_MIN_HOURS = float(xt.get("running_hot_min_hours", NATIVE_BARS_PER_DAY))
    EVENTS_MODE = str(RAW.get("events", {}).get("mode", "event_in_life"))

    costs = RAW.get("costs", {})
    STT_OPT_SELL = float(costs.get("stt_opt_sell", 0.0015))
    STAMP_OPT_BUY = float(costs.get("stamp_opt_buy", 0.00003))
    NSE_OPT = float(costs.get("nse_opt", 0.0003553))
    SEBI = float(costs.get("sebi", 0.000001))
    GST = float(costs.get("gst", 0.18))
    FUT_STT_SELL = float(costs.get("fut_stt_sell", 0.0002))
    FUT_STAMP_BUY = float(costs.get("fut_stamp_buy", 0.00002))

    BACKTESTS = {}
    for i, spec in RAW.get("backtests", {}).items():
        BACKTESTS[str(i).upper()] = BacktestSpec(
            id=str(i).upper(),
            book=str(spec["book"]),
            hedge=bool(spec["hedge"]),
            signal=bool(spec["signal"]),
            var_exit=bool(spec["var_exit"]),
            ex_events=bool(spec["ex_events"]),
            title=str(spec["title"]),
        )
    return RAW


load_file()
