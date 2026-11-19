"""Sina daily-kline provider (money.finance.sina.com.cn, free, no key).

腾讯源之后的免费兜底。接口只返回 date/open/high/low/close/volume（volume 单位为股），
不支持起止日期参数，只能从最新日期往前取 datalen 根再按区间过滤。
"""

from __future__ import annotations

import logging
import os

import pandas as pd
import requests

from integrations.data_source_format import STOCK_HIST_COLUMNS

logger = logging.getLogger(__name__)

_KLINE_URL = "https://money.finance.sina.com.cn/quotes_service/api/json_v2.php/CN_MarketData.getKLineData"
_TIMEOUT_SECONDS = float(os.getenv("SINA_TIMEOUT_SECONDS", "15"))
_RETRY_TIMES = max(int(os.getenv("SINA_RETRY_TIMES", "2")), 1)
_MAX_DATALEN = 1023

_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn",
}


def fetch_stock_sina(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    """拉取日 K（接口固定返回前复权口径），返回 STOCK_HIST_COLUMNS 列的 DataFrame。"""
    code = _sina_symbol(symbol)
    start_d = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
    end_d = f"{end[:4]}-{end[4:6]}-{end[6:8]}"
    span_days = (pd.Timestamp(end_d) - pd.Timestamp(start_d)).days + 2
    datalen = min(max(int(span_days * 1.5), 30), _MAX_DATALEN)

    last_error: Exception | None = None
    rows: list[dict] = []
    for _attempt in range(_RETRY_TIMES):
        try:
            resp = requests.get(
                _KLINE_URL,
                params={"symbol": code, "scale": 240, "ma": "no", "datalen": datalen},
                headers=_HEADERS,
                timeout=_TIMEOUT_SECONDS,
            )
            resp.raise_for_status()
            rows = resp.json()
            break
        except Exception as exc:  # noqa: PERF203 - retry loop
            last_error = exc
    else:
        raise RuntimeError(f"sina retry exhausted: {last_error}")

    if not rows:
        raise RuntimeError("sina empty")
    frame = pd.DataFrame(rows)
    frame = frame[(frame["day"] >= start_d) & (frame["day"] <= end_d)]
    if frame.empty:
        raise RuntimeError("sina empty in range")
    return _to_stock_hist_frame(frame)


def _sina_symbol(symbol: str) -> str:
    code = str(symbol).strip().lower()
    digits = "".join(ch for ch in code if ch.isdigit())
    if code.startswith(("sh", "sz", "bj")) or code.upper().endswith((".SH", ".SZ", ".BJ")):
        return f"{code[:2]}{digits}" if code[:2] in ("sh", "sz", "bj") else _prefix_for(digits)
    return _prefix_for(digits)


def _prefix_for(digits: str) -> str:
    sh_prefix = (
        "600",
        "601",
        "603",
        "605",
        "688",
        "510",
        "511",
        "512",
        "513",
        "515",
        "516",
        "518",
        "560",
        "561",
        "562",
        "563",
    )
    if digits.startswith(sh_prefix) and len(digits) == 6:
        return f"sh{digits}"
    return f"sz{digits}"


def _to_stock_hist_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.copy()
    for col in ("open", "high", "low", "close", "volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    close = frame["close"]
    prev_ref = close.shift(1)
    out = pd.DataFrame(
        {
            "日期": pd.to_datetime(frame["day"]).dt.strftime("%Y-%m-%d"),
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
    return out[list(STOCK_HIST_COLUMNS)].copy()
