"""Two independent VRP books. Loaded from JSON (YAML if PyYAML is installed)."""

from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PKG_DIR = Path(__file__).resolve().parent
DATA_DIR = PKG_DIR / "data"
CACHE_DIR = PKG_DIR / "cache"
CACHE_DIR.mkdir(exist_ok=True)
OUTPUT_DIR = PKG_DIR / "output"
OUTPUT_DIR.mkdir(exist_ok=True)
CHART_DIR = CACHE_DIR / "charts"
CHART_DIR.mkdir(exist_ok=True)
CONFIGS_DIR = PKG_DIR / "configs"
DEFAULT_CONFIG = CONFIGS_DIR / "default.json"

FRAMEWORK_VERSION = 4
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
SCAN_HOUR = 10

MIN_DTE = 8
HEDGE_OPEN_HOUR = 9
NIFTY_STRIKE_STEP = 50.0
NIFTY_LOT_FALLBACK = 65
STOCK_MIN_DTE = 21
STOCK_MAX_DTE = 45
STOCK_EXIT_DTE = 7
STOCK_LOT_FALLBACK = 1
STOCK_STEP_FALLBACK = 5.0

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

RV_WINDOWS = (5, 20, 60, 120)
RV_WEIGHTS = (0.4, 0.3, 0.2, 0.1)
MIN_RV_WINDOWS = 2
COST_BUFFER_MULT = 1.0
MIN_VRP_PTS = 0.25
CALENDAR_TRADING_FRAC = 5.0 / 7.0
MATCHED_VAR_WEIGHT = 0.7
HAR_VAR_WEIGHT = 0.3

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
    global RAW, FRAMEWORK_VERSION, HEDGE_FREQUENCY, HEDGE_UNDERLYING, INDEX, RISK_FREE, DIV_YIELD
    global TRADING_DAYS, NATIVE_BARS_PER_DAY, NATIVE_HOURS, LOOKBACK_DAYS, TARGET_CAPITAL, SCAN_HOUR
    global MIN_DTE, HEDGE_OPEN_HOUR, NIFTY_STRIKE_STEP, NIFTY_LOT_FALLBACK
    global STOCK_MIN_DTE, STOCK_MAX_DTE, STOCK_EXIT_DTE, STOCK_LOT_FALLBACK, STOCK_STEP_FALLBACK
    global DEFAULT_LOTS, DEFAULT_STEPS, SLIPPAGE_FRAC, USE_BID_ASK, STRESS_FRAC, EM_MULT, MAX_LOTS
    global MARGIN_SHORT_PCT, MARGIN_FUT_PCT, MARGIN_STOCK_PCT, ELM_INDEX, ELM_STOCK
    global SPAN_SHORT_PCT_INDEX, SPAN_SHORT_PCT_STOCK
    global RV_WINDOWS, RV_WEIGHTS, MIN_RV_WINDOWS, COST_BUFFER_MULT, MIN_VRP_PTS
    global CALENDAR_TRADING_FRAC, MATCHED_VAR_WEIGHT, HAR_VAR_WEIGHT
    global CRUSH_FRAC, RUNNING_HOT_MULT, RUNNING_HOT_MIN_HOURS, EVENTS_MODE
    global STT_OPT_SELL, STAMP_OPT_BUY, NSE_OPT, SEBI, GST, FUT_STT_SELL, FUT_STAMP_BUY

    p = Path(path) if path is not None else DEFAULT_CONFIG
    RAW = _parse(p)
    FRAMEWORK_VERSION = int(RAW.get("framework_version", 4))
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
    SCAN_HOUR = int(RAW.get("scan_hour", 10))

    ib = RAW.get("books", {}).get("index", {})
    sb = RAW.get("books", {}).get("stock", {})
    MIN_DTE = int(ib.get("min_dte", 8))
    HEDGE_OPEN_HOUR = int(ib.get("hedge_open_hour", 9))
    NIFTY_STRIKE_STEP = float(ib.get("strike_step", 50.0))
    NIFTY_LOT_FALLBACK = int(ib.get("lot_fallback", 65))
    STOCK_MIN_DTE = int(sb.get("min_dte", 21))
    STOCK_MAX_DTE = int(sb.get("max_dte", 45))
    STOCK_EXIT_DTE = int(sb.get("exit_dte", 7))
    STOCK_LOT_FALLBACK = int(RAW.get("stock_lot_fallback", 1))
    STOCK_STEP_FALLBACK = float(RAW.get("stock_step_fallback", 5.0))

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
    RV_WINDOWS = tuple(int(x) for x in sig.get("windows", [5, 20, 60, 120]))
    RV_WEIGHTS = tuple(float(x) for x in sig.get("weights", [0.4, 0.3, 0.2, 0.1]))
    MIN_RV_WINDOWS = int(sig.get("min_windows", 2))
    COST_BUFFER_MULT = float(sig.get("cost_buffer_mult", 1.0))
    MIN_VRP_PTS = float(sig.get("min_vrp_pts", 0.25))
    CALENDAR_TRADING_FRAC = float(sig.get("calendar_trading_frac", 5.0 / 7.0))
    MATCHED_VAR_WEIGHT = float(sig.get("matched_var_weight", 0.7))
    HAR_VAR_WEIGHT = float(sig.get("har_var_weight", 0.3))

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
    return RAW


load_file()
