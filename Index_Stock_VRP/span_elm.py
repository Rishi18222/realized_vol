"""SPAN/ELM-style margins without importing Calendar_Dispersion_BT (cache-only safe).

ELM rates match the calendar-dispersion book: 2% index, 3.5% stock on |delta| notional.
SPAN uses NSE clearing XML risk arrays when a zip is on disk; otherwise a short-option % proxy.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path

import numpy as np
import pandas as pd

from . import config as C
from .pricing import straddle_unit, years_to

SPAN_DIR = C.REPO_ROOT / "Calendar_Dispersion_BT" / "cache" / "span"


@dataclass
class SpanMargin:
    span: float
    elm: float
    posted: float
    matched: int
    source: str
    asof: str
    missing: list[str]


def _zip_path(day: datetime) -> Path:
    return SPAN_DIR / f"nsccl.{day.strftime('%Y%m%d')}.s.zip"


def find_span_zip(day: datetime) -> Path | None:
    d = pd.Timestamp(day).to_pydatetime()
    for i in range(6):
        cur = d - timedelta(days=i)
        if cur.weekday() >= 5:
            continue
        path = _zip_path(cur)
        if path.exists() and path.stat().st_size > 1000:
            return path
    return None


def _floats_a(ra_xml: str) -> list[float]:
    vals = [float(x) for x in re.findall(r"<a>([^<]+)</a>", ra_xml)]
    return vals[:16]


def _pf_block(raw: str, tag: str, code: str) -> str | None:
    m = re.search(
        rf"<{tag}Pf>\s*<pfId>\d+</pfId>\s*<pfCode>{re.escape(code)}</pfCode>.*?</{tag}Pf>",
        raw,
        re.S,
    )
    return m.group(0) if m else None


def _parse_opts(block: str) -> dict[tuple[str, str, float], dict]:
    out: dict[tuple[str, str, float], dict] = {}
    parts = re.split(r"<series>", block)
    for part in parts[1:]:
        pe = re.search(r"<pe>(\d{8})</pe>", part)
        if not pe:
            continue
        exp = f"{pe.group(1)[:4]}-{pe.group(1)[4:6]}-{pe.group(1)[6:8]}"
        for om in re.finditer(r"<opt>(.*?)</opt>", part, re.S):
            body = om.group(1)
            o = re.search(r"<o>([CP])</o>", body)
            k = re.search(r"<k>([^<]+)</k>", body)
            ra = re.search(r"<ra>(.*?)</ra>", body, re.S)
            if not (o and k and ra):
                continue
            arr = _floats_a(ra.group(1))
            if len(arr) < 16:
                continue
            d = re.search(r"<d>([^<]+)</d>", body)
            out[(exp, o.group(1), round(float(k.group(1)), 2))] = {
                "ra": arr,
                "delta": float(d.group(1)) if d else 0.0,
            }
    return out


def _parse_futs(block: str) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for fm in re.finditer(r"<fut>(.*?)</fut>", block, re.S):
        body = fm.group(1)
        pe = re.search(r"<pe>(\d{8})</pe>", body)
        ra = re.search(r"<ra>(.*?)</ra>", body, re.S)
        if not (pe and ra):
            continue
        exp = f"{pe.group(1)[:4]}-{pe.group(1)[4:6]}-{pe.group(1)[6:8]}"
        arr = _floats_a(ra.group(1))
        if len(arr) < 16:
            continue
        d = re.search(r"<d>([^<]+)</d>", body)
        out[exp] = {"ra": arr, "delta": float(d.group(1)) if d else 1.0}
    return out


@lru_cache(maxsize=64)
def _load_raw(path_str: str) -> str:
    path = Path(path_str)
    with zipfile.ZipFile(path) as zf:
        name = next(n for n in zf.namelist() if n.endswith(".spn") or n.endswith(".xml"))
        return zf.read(name).decode("latin-1")


@lru_cache(maxsize=256)
def _opts_cached(path_str: str, symbol: str) -> dict:
    raw = _load_raw(path_str)
    oop = _pf_block(raw, "oop", symbol)
    return _parse_opts(oop) if oop else {}


@lru_cache(maxsize=256)
def _futs_cached(path_str: str, symbol: str) -> dict:
    raw = _load_raw(path_str)
    block = _pf_block(raw, "fut", symbol)
    return _parse_futs(block) if block else {}


def _opt_lookup(table: dict, expiry: str, side: str, k: float) -> dict | None:
    hits = [(e, o, kk) for (e, o, kk) in table if o == side and e.replace("-", "") == str(expiry).replace("-", "")]
    if not hits:
        return None
    kk = min((h[2] for h in hits), key=lambda x: abs(x - k))
    if abs(kk - k) > 1.01:
        return None
    exp = next(h[0] for h in hits if h[2] == kk)
    return table[(exp, side, kk)]


def _xml_margin(
    symbol: str,
    expiry: str,
    k: float,
    lots: int,
    lot: int,
    fut_units: float,
    asof,
    *,
    is_index: bool,
    spot: float,
    book_side: str = "short",
) -> SpanMargin | None:
    path = find_span_zip(pd.Timestamp(asof).to_pydatetime())
    if path is None:
        return None
    table = _opts_cached(str(path), symbol)
    if not table:
        return None
    units = (1 if book_side == "long" else -1) * abs(int(lots) * int(lot))
    ra = np.zeros(16)
    net_delta = 0.0
    matched = 0
    missing: list[str] = []
    for cp in ("C", "P"):
        rec = _opt_lookup(table, expiry, cp, float(k))
        if rec is None:
            missing.append(f"{symbol} {expiry} {cp} {k}")
            continue
        ra += units * np.array(rec["ra"], dtype=float)
        net_delta += units * float(rec["delta"])
        matched += 1
    ftab = _futs_cached(str(path), C.INDEX if is_index else symbol)
    if abs(fut_units) > 1e-9:
        if ftab:
            exp = min(ftab)
            rec = ftab[exp]
            ra += float(fut_units) * np.array(rec["ra"], dtype=float)
            net_delta += float(fut_units) * float(rec["delta"])
            matched += 1
        else:
            missing.append("fut")
    if matched == 0:
        return None
    span = float(max(0.0, -float(np.min(ra))))
    elm_rate = C.ELM_INDEX if is_index else C.ELM_STOCK
    elm = float(elm_rate * abs(net_delta) * float(spot))
    asof_s = path.name.split(".")[1]
    asof_s = f"{asof_s[:4]}-{asof_s[4:6]}-{asof_s[6:8]}"
    return SpanMargin(
        span=span,
        elm=elm,
        posted=span + elm,
        matched=matched,
        source="nse_span_xml",
        asof=asof_s,
        missing=missing,
    )


def _proxy_margin(
    spot: float,
    lots: int,
    lot: int,
    fut_units: float,
    *,
    is_index: bool,
    asof: str,
    delta_units: float,
) -> SpanMargin:
    span_pct = C.SPAN_SHORT_PCT_INDEX if is_index else C.SPAN_SHORT_PCT_STOCK
    fut_pct = C.MARGIN_FUT_PCT if is_index else C.MARGIN_STOCK_PCT
    elm_rate = C.ELM_INDEX if is_index else C.ELM_STOCK
    span = span_pct * float(spot) * abs(int(lots) * int(lot))
    fut = fut_pct * float(spot) * abs(float(fut_units))
    elm = elm_rate * abs(float(delta_units)) * float(spot)
    posted = span + fut + elm
    return SpanMargin(
        span=span + fut,
        elm=elm,
        posted=posted,
        matched=0,
        source="elm_proxy",
        asof=asof,
        missing=["span zip missing or unmatched → short-option % + ELM"],
    )


def margin_straddle(
    symbol: str,
    expiry: str,
    k: float,
    lots: int,
    lot: int,
    spot: float,
    iv: float,
    ts,
    fut_units: float,
    *,
    is_index: bool,
    book_side: str = "short",
) -> SpanMargin:
    t = years_to(pd.Timestamp(ts), expiry)
    g = straddle_unit(spot, k, t, iv)
    sign = 1.0 if book_side == "long" else -1.0
    delta_units = float(g["delta"]) * sign * int(lots) * int(lot) + float(fut_units)
    xml = _xml_margin(
        symbol, expiry, k, lots, lot, fut_units, ts, is_index=is_index, spot=spot, book_side=book_side
    )
    if xml is not None:
        return xml
    return _proxy_margin(
        spot,
        lots,
        lot,
        fut_units,
        is_index=is_index,
        asof=str(pd.Timestamp(ts).date()),
        delta_units=delta_units,
    )


margin_short_straddle = margin_straddle
