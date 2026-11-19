"""港股/美股日线 provider（腾讯行情，免 key）。

A 股已有完整回退链；本模块用腾讯公开的
kline / fqkline 接口补齐这条能力，返回列与
:data:`integrations.data_source_format.STOCK_HIST_COLUMNS` 一致。

港股走 ``appstock/app/kline/kline``（不复权），美股走 ``appstock/app/fqkline/get``
（支持 qfq/hfq）。两者接口都不提供成交额/换手率，置 NA；成交量按“股”口径返回。
"""

from __future__ import annotations

import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from typing import Any

import pandas as pd
import requests

from integrations.data_source_format import STOCK_HIST_COLUMNS, tag_source

logger = logging.getLogger(__name__)

_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/kline/kline"
_FQKLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
_TIMEOUT_SECONDS = float(os.getenv("TENCENT_HK_US_TIMEOUT_SECONDS", "15"))
_RETRY_TIMES = max(int(os.getenv("TENCENT_HK_US_RETRY_TIMES", "2")), 1)
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def normalize_hk_us_symbol(symbol: str) -> str:
    """返回规范代码（``00700.HK`` / ``AAPL.US``）；非港美股返回空串。"""
    raw = str(symbol or "").strip()
    upper = raw.upper()
    if upper.endswith(".HK") or upper.startswith("HK") and not upper.endswith(".US"):
        digits = "".join(ch for ch in raw if ch.isdigit())
        if digits:
            return f"{digits.zfill(5)}.HK"
        return ""
    if upper.endswith(".US"):
        ticker = re.sub(r"[^A-Z0-9.\-]", "", upper[:-3])
        return f"{ticker}.US" if ticker else ""
    if upper.startswith("US"):
        ticker = re.sub(r"[^A-Z0-9.\-]", "", upper[2:])
        return f"{ticker}.US" if ticker else ""
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9.\-]{0,7}", raw):
        return f"{upper}.US"
    return ""


def is_hk_us_symbol(symbol: str) -> bool:
    return bool(normalize_hk_us_symbol(symbol))


def _tencent_code(normalized: str) -> str:
    if normalized.endswith(".HK"):
        return f"hk{normalized[:-3]}"
    return f"us{normalized[:-3]}"


def _date_text(value: str | date) -> str:
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = str(value or "").replace("-", "").strip()
    return text[:8]


def _iso_date(text: str) -> str:
    text = str(text or "")[:10]
    return f"{text[:4]}-{text[4:6]}-{text[6:8]}" if len(text) >= 8 and text[:8].isdigit() else text


def _adjust_mode(adjust: str) -> str:
    mapped = {"hfq": "hfq", "backward": "hfq", "qfq": "qfq", "forward": "qfq"}
    return mapped.get(str(adjust or "").strip().lower(), "")


def fetch_stock_hk_us(symbol: str, start: str, end: str, adjust: str = "qfq") -> pd.DataFrame:
    """拉取港股/美股日 K，返回 STOCK_HIST_COLUMNS 列。"""
    normalized = normalize_hk_us_symbol(symbol)
    if not normalized:
        raise RuntimeError(f"unsupported hk/us symbol: {symbol}")
    code = _tencent_code(normalized)
    start_text, end_text = _date_text(start), _date_text(end)
    start_iso, end_iso = _iso_date(start_text), _iso_date(end_text)
    span_days = max((pd.Timestamp(end_iso) - pd.Timestamp(start_iso)).days + 2, 10)
    count = min(max(int(span_days * 1.5), 30), 800)

    last_error: Exception | None = None
    rows: list[list] = []
    for _attempt in range(_RETRY_TIMES):
        try:
            rows = _request_kline(code, normalized, start_iso, end_iso, count, adjust)
            break
        except Exception as exc:  # noqa: PERF203 - bounded retry
            last_error = exc
    else:
        raise RuntimeError(f"tencent hk/us retry exhausted: {last_error}")
    if not rows:
        raise RuntimeError(f"tencent hk/us empty: {normalized}")
    return _to_stock_hist_frame(rows, start_iso, end_iso)


def fetch_histories_batch(
    symbols: list[str],
    start: str,
    end: str,
    adjust: str = "qfq",
    max_workers: int = 8,
) -> dict[str, pd.DataFrame]:
    """逐只并发拉取；失败的标的跳过，不拖垮整批。"""
    result: dict[str, pd.DataFrame] = {}

    def _one(symbol: str) -> tuple[str, pd.DataFrame | None]:
        try:
            return symbol, fetch_stock_hk_us(symbol, start, end, adjust)
        except Exception as exc:
            logger.warning("hk/us hist failed: %s: %s", symbol, type(exc).__name__)
            return symbol, None

    with ThreadPoolExecutor(max_workers=max(int(max_workers or 1), 1)) as executor:
        for symbol, df in executor.map(_one, list(symbols)):
            if df is not None and not df.empty:
                result[symbol] = df
    return result


def fetch_latest_quote(symbol: str) -> dict[str, Any] | None:
    normalized = normalize_hk_us_symbol(symbol)
    if not normalized:
        return None
    end_d = date.today()
    start_d = end_d - timedelta(days=60)
    try:
        df = fetch_stock_hk_us(normalized, start_d.strftime("%Y%m%d"), end_d.strftime("%Y%m%d"), "qfq")
    except Exception as exc:
        logger.debug("hk/us quote failed: %s: %s", normalized, type(exc).__name__)
        return None
    if df.empty:
        return None
    last, prev = df.iloc[-1], (df.iloc[-2] if len(df) > 1 else None)
    close = _safe_float(last.get("收盘"))
    prev_close = _safe_float(prev.get("收盘")) if prev is not None else None
    return {
        "code": normalized,
        "name": "",
        "last_price": close,
        "prev_close": prev_close,
        "open": _safe_float(last.get("开盘")),
        "high": _safe_float(last.get("最高")),
        "low": _safe_float(last.get("最低")),
        "volume": _safe_float(last.get("成交量")),
        "amount": _safe_float(last.get("成交额")),
        "pct_chg": _safe_float(last.get("涨跌幅")),
    }


def fetch_quote_map(symbols: list[str]) -> dict[str, dict[str, Any]]:
    out: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        quote = fetch_latest_quote(symbol)
        if quote:
            out[str(quote["code"])] = quote
    return out


def _request_kline(
    code: str,
    normalized: str,
    start_iso: str,
    end_iso: str,
    count: int,
    adjust: str,
) -> list[list]:
    mode = _adjust_mode(adjust)
    if normalized.endswith(".HK"):
        resp = requests.get(
            _KLINE_URL,
            params={"param": f"{code},day,{start_iso},{end_iso},{count}"},
            headers=_HEADERS,
            timeout=_TIMEOUT_SECONDS,
        )
        resp.raise_for_status()
        payload = resp.json()
        node = (payload.get("data") or {}).get(code) or {}
        rows = node.get("day") or []
        if not rows:
            raise RuntimeError("tencent hk no kline rows")
        return rows

    if mode:
        param = f"{code},day,{start_iso},{end_iso},{count},{mode}"
    else:
        param = f"{code},day,{start_iso},{end_iso},{count}"
    resp = requests.get(_FQKLINE_URL, params={"param": param}, headers=_HEADERS, timeout=_TIMEOUT_SECONDS)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") not in (0, None):
        raise RuntimeError(f"tencent us code={payload.get('code')}")
    node = (payload.get("data") or {}).get(code) or {}
    for key in (f"{mode}day" if mode else "", "qfqday", "hfqday", "day"):
        if key and node.get(key):
            return node[key]
    raise RuntimeError("tencent us no kline rows")


def _to_stock_hist_frame(rows: list[list], start_iso: str, end_iso: str) -> pd.DataFrame:
    frame = pd.DataFrame(
        [row[:6] for row in rows if isinstance(row, (list, tuple)) and len(row) >= 6],
        columns=["date", "open", "close", "high", "low", "volume"],
    )
    if frame.empty:
        raise RuntimeError("tencent hk/us empty frame")
    for col in ("open", "close", "high", "low", "volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["date"] = frame["date"].map(_iso_date)
    frame = frame[(frame["date"] >= start_iso) & (frame["date"] <= end_iso)]
    if frame.empty:
        raise RuntimeError("tencent hk/us empty in range")
    close = frame["close"]
    prev_ref = close.shift(1)
    out = pd.DataFrame(
        {
            "日期": frame["date"],
            "开盘": frame["open"],
            "最高": frame["high"],
            "最低": frame["low"],
            "收盘": close,
            "成交量": frame["volume"],
            "成交额": pd.NA,
            "涨跌幅": (close / prev_ref - 1.0) * 100.0,
            "换手率": pd.NA,
            "振幅": (frame["high"] - frame["low"]) / prev_ref * 100.0,
        }
    )
    return tag_source(out[list(STOCK_HIST_COLUMNS)].copy(), "tencent_hk_us")


def _safe_float(value: Any) -> float | None:
    if value is None or pd.isna(value):
        return None
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if pd.notna(result) else None
