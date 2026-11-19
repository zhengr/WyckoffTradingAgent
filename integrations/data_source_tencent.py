"""Tencent daily-kline provider (web.ifzq.gtimg.cn, free, no key).

海外网络可达（东财/新浪部分接口会掐断海外连接，腾讯此接口实测稳定），作为
akshare/efinance 在海外 CI 环境不可用时的免费兜底源。返回列与
:data:`integrations.data_source_format.STOCK_HIST_COLUMNS` 对齐；
成交额/换手率/振幅接口未提供，置 NA，与 efinance 的兜底口径一致。
"""

from __future__ import annotations

import logging
import os

import pandas as pd
import requests

from integrations.data_source_format import STOCK_HIST_COLUMNS

logger = logging.getLogger(__name__)

_KLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/fqkline/get"
_TIMEOUT_SECONDS = float(os.getenv("TENCENT_TIMEOUT_SECONDS", "15"))
_RETRY_TIMES = max(int(os.getenv("TENCENT_RETRY_TIMES", "2")), 1)

_SH_PREFIX = ("600", "601", "603", "605", "688", "510", "511", "512", "513", "515", "516", "518", "560", "561", "562", "563")
_BJ_PREFIX = ("43", "83", "87", "920")

_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_stock_tencent(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
    """拉取日 K（qfq/hfq/不复权），返回 STOCK_HIST_COLUMNS 列的 DataFrame。"""
    code = _tencent_symbol(symbol)
    mode = _adjust_mode(adjust)
    start_d = f"{start[:4]}-{start[4:6]}-{start[6:8]}"
    end_d = f"{end[:4]}-{end[4:6]}-{end[6:8]}"
    span_days = max((pd.Timestamp(end_d) - pd.Timestamp(start_d)).days + 2, 10)
    count = min(max(int(span_days * 1.5), 30), 800)

    last_error: Exception | None = None
    for _attempt in range(_RETRY_TIMES):
        try:
            rows = _request_kline(code, mode, start_d, end_d, count)
            break
        except Exception as exc:  # noqa: PERF203 - retry loop
            last_error = exc
    else:
        raise RuntimeError(f"tencent retry exhausted: {last_error}")

    frame = pd.DataFrame(rows, columns=["date", "open", "close", "high", "low", "volume"])
    for col in ("open", "close", "high", "low", "volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame["date"] = frame["date"].astype(str)
    frame = frame[(frame["date"] >= start_d) & (frame["date"] <= end_d)]
    if frame.empty:
        raise RuntimeError("tencent empty in range")
    return _to_stock_hist_frame(frame)


def _request_kline(code: str, mode: str, start_d: str, end_d: str, count: int) -> list[list]:
    if code.startswith("bj"):
        raise RuntimeError("tencent no BSE kline")
    if code.startswith("hk"):
        return _request_hk_kline(code, start_d, end_d, count)
    param = f"{code},day,{start_d},{end_d},{count},{mode}" if mode else f"{code},day,{start_d},{end_d},{count}"
    resp = requests.get(_KLINE_URL, params={"param": param}, headers=_HEADERS, timeout=_TIMEOUT_SECONDS)
    resp.raise_for_status()
    payload = resp.json()
    if payload.get("code") != 0:
        raise RuntimeError(f"tencent code={payload.get('code')}")
    node = (payload.get("data") or {}).get(code) or {}
    for key in (f"{mode}day", "day", "qfqday", "hfqday"):
        rows = node.get(key)
        if rows:
            return rows
    raise RuntimeError("tencent no kline rows")


def _request_hk_kline(code: str, start_d: str, end_d: str, count: int) -> list[list]:
    """港股没有 fqkline 口径，走 /appstock/app/kline/kline（不复权）。"""
    resp = requests.get(
        "https://web.ifzq.gtimg.cn/appstock/app/kline/kline",
        params={"param": f"{code},day,{start_d},{end_d},{count}"},
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


def _tencent_symbol(symbol: str) -> str:
    raw = str(symbol).strip().lower()
    # 港股：00700.HK / hk00700 / 700.HK
    if raw.endswith(".hk") or raw.startswith("hk"):
        digits = "".join(ch for ch in raw if ch.isdigit()).zfill(5)
        return f"hk{digits}"
    # 显式前缀
    for prefix in ("sh", "sz", "bj"):
        if raw.startswith(prefix):
            digits = "".join(ch for ch in raw[len(prefix):] if ch.isdigit())
            return f"{prefix}{digits}"
    digits = "".join(ch for ch in raw.split(".")[0] if ch.isdigit())
    if digits.startswith(_BJ_PREFIX) and len(digits) == 6:
        return f"bj{digits}"
    if digits.startswith(_SH_PREFIX) and len(digits) == 6:
        return f"sh{digits}"
    return f"sz{digits}"


def _adjust_mode(adjust: str) -> str:
    mapped = {"qfq": "qfq", "forward": "qfq", "hfq": "hfq", "backward": "hfq"}
    return mapped.get(str(adjust or "").strip().lower(), "")


def _to_stock_hist_frame(frame: pd.DataFrame) -> pd.DataFrame:
    close = frame["close"]
    prev_ref = close.shift(1)
    pct = (close / prev_ref - 1.0) * 100.0
    out = pd.DataFrame(
        {
            "日期": pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d"),
            "开盘": frame["open"],
            "最高": frame["high"],
            "最低": frame["low"],
            "收盘": close,
            # 腾讯 volume 单位是手（A股 1 手 = 100 股），转成股与其它源对齐
            "成交量": frame["volume"] * 100.0,
            "成交额": pd.NA,
            "涨跌幅": pct,
            "换手率": pd.NA,
            "振幅": (frame["high"] - frame["low"]) / prev_ref * 100.0,
        }
    )
    return out[list(STOCK_HIST_COLUMNS)].copy()
