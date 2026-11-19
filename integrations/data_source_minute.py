"""分钟线 provider（A 股 akshare / 港股腾讯），免 key。

提供 ``/v1/klines/intraday`` 的等价能力与历史分钟线能力。

- A 股：akshare ``stock_zh_a_hist_min_em``（period=1/5/15/30/60）。
- 港股：腾讯 ``appstock/app/kline/mkline``（m5/m15/m30/m60，无 1m）。
- 美股：腾讯分钟接口不可用，本模块不支持（调用会抛错）。

返回统一的 DataFrame：``datetime``（tz-aware Asia/Shanghai）、``open/high/low/close/volume/
amount``、``date``（YYYY-MM-DD）、``pct_chg``、``turnover``。``amount`` 缺失时置 NA，
由 ``core.intraday_analysis.ensure_intraday_df`` 用 close*volume 兜底。
"""

from __future__ import annotations

import logging
import os
import re
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd
import requests

logger = logging.getLogger(__name__)

CN_TZ = ZoneInfo("Asia/Shanghai")
_MKLINE_URL = "https://web.ifzq.gtimg.cn/appstock/app/kline/mkline"
_TIMEOUT_SECONDS = float(os.getenv("MINUTE_TENCENT_TIMEOUT_SECONDS", "15"))
_RETRY_TIMES = max(int(os.getenv("MINUTE_RETRY_TIMES", "2")), 1)
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
_PERIODS = {"1", "5", "15", "30", "60"}


def _norm_period(period: str) -> str:
    text = str(period or "").strip().lower().removesuffix("m")
    if text not in _PERIODS:
        raise RuntimeError(f"unsupported minute period: {period}")
    return text


def _is_hk(symbol: str) -> bool:
    upper = str(symbol or "").upper()
    return upper.endswith(".HK") or upper.startswith("HK")


def _is_us(symbol: str) -> bool:
    from integrations.data_source_hk_us import is_hk_us_symbol, normalize_hk_us_symbol

    normalized = normalize_hk_us_symbol(symbol)
    return is_hk_us_symbol(symbol) and normalized.endswith(".US")


def fetch_minute_hist(
    symbol: str,
    period: str = "5",
    start: str | None = None,
    end: str | None = None,
    adjust: str = "",
    count: int | None = None,
) -> pd.DataFrame:
    """历史分钟线（可跨多日）。start/end 支持 'YYYYMMDD'、'YYYY-MM-DD' 或带时分。"""
    p = _norm_period(period)
    if _is_us(symbol):
        raise RuntimeError("美股分钟线暂无可用数据源（腾讯不提供 us 分钟 K）")
    if _is_hk(symbol):
        return _fetch_hk_minute(symbol, p, start, end, count)
    return _fetch_cn_minute(symbol, p, start, end, adjust, count)


def fetch_intraday(symbol: str, period: str = "1m", count: int = 500) -> pd.DataFrame:
    """当日分钟线（盘中）。"""
    p = _norm_period(period)
    today = date.today().strftime("%Y-%m-%d")
    df = fetch_minute_hist(symbol, period=p, start=f"{today} 00:00", end=f"{today} 23:59")
    if count and len(df) > int(count):
        df = df.tail(int(count))
    return df.reset_index(drop=True)


def fetch_minutes_batch(
    symbols: list[str],
    period: str = "5",
    count: int | None = None,
    max_workers: int = 8,
) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}

    def _one(symbol: str) -> tuple[str, pd.DataFrame | None]:
        try:
            return symbol, fetch_minute_hist(symbol, period=period, count=count)
        except Exception as exc:
            logger.debug("minute hist failed: %s: %s", symbol, type(exc).__name__)
            return symbol, None

    with ThreadPoolExecutor(max_workers=max(int(max_workers or 1), 1)) as executor:
        for symbol, df in executor.map(_one, list(symbols)):
            if df is not None and not df.empty:
                out[symbol] = df
    return out


def intraday_entry_price_fetcher() -> Callable[[str, date, str, dict], tuple[float | None, str]] | None:
    """历史交易日分钟入场价 fetcher，替代旧付费源的历史 1m 回测口径。"""
    from core.backtest_execution import price_at_or_before

    def _fetch(code: str, day: date, entry_time: str, _cache: dict) -> tuple[float | None, str]:
        start_text = f"{day.strftime('%Y-%m-%d')} 09:30"
        end_text = f"{day.strftime('%Y-%m-%d')} 15:05"
        df = fetch_minute_hist(code, period="1", start=start_text, end=end_text)
        return price_at_or_before(df, day, entry_time), f"minute_1m_{entry_time}"

    return _fetch


def _fetch_cn_minute(
    symbol: str,
    period: str,
    start: str | None,
    end: str | None,
    adjust: str,
    count: int | None,
) -> pd.DataFrame:
    import akshare as ak

    start_text = _datetime_text(start, day_start=True) or "1979-09-01 09:32:00"
    end_text = _datetime_text(end, day_start=False) or "2222-01-01 09:32:00"
    last_error: Exception | None = None
    for _attempt in range(_RETRY_TIMES):
        try:
            df = ak.stock_zh_a_hist_min_em(
                symbol=symbol,
                period=period,
                start_date=start_text,
                end_date=end_text,
                adjust=adjust or "",
            )
            break
        except Exception as exc:  # noqa: PERF203 - bounded retry
            last_error = exc
    else:
        raise RuntimeError(f"akshare minute retry exhausted: {last_error}")
    if df is None or df.empty:
        raise RuntimeError("akshare minute empty")
    return _normalize_cn_minute(df, count)


def _fetch_hk_minute(
    symbol: str,
    period: str,
    start: str | None,
    end: str | None,
    count: int | None,
) -> pd.DataFrame:
    digits = "".join(ch for ch in str(symbol) if ch.isdigit()).zfill(5)
    code = f"hk{digits}"
    param = f"{code},m{period},,320"
    last_error: Exception | None = None
    for _attempt in range(_RETRY_TIMES):
        try:
            resp = requests.get(_MKLINE_URL, params={"param": param}, headers=_HEADERS, timeout=_TIMEOUT_SECONDS)
            resp.raise_for_status()
            payload = resp.json()
            node = (payload.get("data") or {}).get(code) or {}
            rows = node.get(f"m{period}") or []
            break
        except Exception as exc:  # noqa: PERF203 - bounded retry
            last_error = exc
    else:
        raise RuntimeError(f"tencent hk minute retry exhausted: {last_error}")
    if not rows:
        raise RuntimeError("tencent hk minute empty")
    frame = pd.DataFrame(
        [row[:6] for row in rows if isinstance(row, (list, tuple)) and len(row) >= 6],
        columns=["time", "open", "close", "high", "low", "volume"],
    )
    frame["datetime"] = pd.to_datetime(frame["time"].astype(str).str.replace("/", "-"), errors="coerce")
    for col in ("open", "close", "high", "low", "volume"):
        frame[col] = pd.to_numeric(frame[col], errors="coerce")
    frame = frame.dropna(subset=["datetime"])
    frame["datetime"] = frame["datetime"].dt.tz_localize(CN_TZ, nonexistent="shift_forward", ambiguous="NaT")
    start_dt, end_dt = _bounds(start, end)
    if start_dt is not None:
        frame = frame[frame["datetime"] >= start_dt]
    if end_dt is not None:
        frame = frame[frame["datetime"] <= end_dt]
    if frame.empty:
        raise RuntimeError("tencent hk minute empty in range")
    if count and len(frame) > int(count):
        frame = frame.tail(int(count))
    return _to_minute_frame(frame)


def _normalize_cn_minute(df: pd.DataFrame, count: int | None) -> pd.DataFrame:
    work = df.copy()
    rename = {}
    for src, dst in (
        ("时间", "datetime"),
        ("开盘", "open"),
        ("最高", "high"),
        ("最低", "low"),
        ("收盘", "close"),
        ("成交量", "volume"),
        ("成交额", "amount"),
        ("涨跌幅", "pct_chg"),
        ("换手率", "turnover"),
    ):
        for column in work.columns:
            if str(column) == src or str(column).startswith(src):
                rename[column] = dst
                break
    work = work.rename(columns=rename)
    if "datetime" not in work.columns:
        raise RuntimeError("akshare minute missing 时间列")
    work["datetime"] = pd.to_datetime(work["datetime"], errors="coerce")
    work["datetime"] = work["datetime"].dt.tz_localize(CN_TZ, nonexistent="shift_forward", ambiguous="NaT")
    for col in ("open", "high", "low", "close", "volume", "amount", "pct_chg", "turnover"):
        if col not in work.columns:
            work[col] = pd.NA
        work[col] = pd.to_numeric(work[col], errors="coerce")
    work = work.dropna(subset=["datetime", "close"]).sort_values("datetime")
    if count and len(work) > int(count):
        work = work.tail(int(count))
    return _to_minute_frame(work.reset_index(drop=True))


def _to_minute_frame(frame: pd.DataFrame) -> pd.DataFrame:
    frame = frame.sort_values("datetime").reset_index(drop=True)
    out = pd.DataFrame(
        {
            "datetime": frame["datetime"],
            "date": frame["datetime"].dt.strftime("%Y-%m-%d"),
            "open": frame["open"],
            "high": frame["high"],
            "low": frame["low"],
            "close": frame["close"],
            "volume": frame["volume"],
            "amount": frame.get("amount", pd.Series(pd.NA, index=frame.index)),
            "pct_chg": frame.get("pct_chg", pd.Series(pd.NA, index=frame.index)),
            "turnover": frame.get("turnover", pd.Series(pd.NA, index=frame.index)),
        }
    )
    return out


def _datetime_text(value: str | None, *, day_start: bool) -> str:
    if not value:
        return ""
    text = str(value).strip().replace("/", "-").replace("T", " ")
    if re.fullmatch(r"\d{8}", text):
        return f"{text[:4]}-{text[4:6]}-{text[6:8]} {'09:30:00' if day_start else '23:59:59'}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
        return f"{text} {'09:30:00' if day_start else '23:59:59'}"
    if re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}(:\d{2})?", text):
        if not text.endswith(tuple(f":{s:02d}" for s in range(60))):
            text = f"{text}:00"
        return text
    return ""


def _bounds(start: str | None, end: str | None) -> tuple[Any, Any]:
    start_dt = pd.to_datetime(_datetime_text(start, day_start=True), errors="coerce") if start else None
    end_dt = pd.to_datetime(_datetime_text(end, day_start=False), errors="coerce") if end else None
    if start_dt is not None and pd.notna(start_dt) and start_dt.tzinfo is None:
        start_dt = start_dt.tz_localize(CN_TZ)
    if end_dt is not None and pd.notna(end_dt) and end_dt.tzinfo is None:
        end_dt = end_dt.tz_localize(CN_TZ)
    return start_dt, end_dt
