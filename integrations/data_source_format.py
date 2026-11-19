"""Shared stock-history formatting helpers."""

from __future__ import annotations

import re
from datetime import date

import pandas as pd


def compact_error(exc: Exception, max_len: int = 120) -> str:
    msg = str(exc or "").strip().replace("\n", " ")
    msg = re.sub(r"\s+", " ", msg)
    if len(msg) > max_len:
        msg = msg[: max_len - 3] + "..."
    return f"{type(exc).__name__}: {msg}" if msg else type(exc).__name__


STOCK_HIST_COLUMNS = (
    "日期",
    "开盘",
    "最高",
    "最低",
    "收盘",
    "成交量",
    "成交额",
    "涨跌幅",
    "换手率",
    "振幅",
)
SH_PREFIXES = (
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


def to_ts_code(symbol: str) -> str:
    code = str(symbol).strip()
    if "." in code:
        return code
    return f"{code}.SH" if code.startswith(SH_PREFIXES) else f"{code}.SZ"


def normalize_cn_exchange_code(symbol: str) -> str:
    """6 位 A 股代码 → 带交易所后缀代码（.SH/.SZ/.BJ），已是后缀形式则原样返回。"""
    raw = str(symbol or "").strip().upper()
    if not raw:
        return ""
    if "." in raw and len(raw.split(".", 1)[0]) == 6:
        return raw
    digits = "".join(ch for ch in raw if ch.isdigit())
    if len(digits) != 6:
        return raw
    if digits.startswith(("0", "1", "2", "3")):
        return f"{digits}.SZ"
    if digits.startswith(("4", "8", "9")):
        return f"{digits}.BJ"
    return f"{digits}.SH"


def tag_source(df: pd.DataFrame, source: str) -> pd.DataFrame:
    df.attrs["source"] = source
    return df


def hist_date_text(value: str | date) -> str:
    return value.strftime("%Y%m%d") if isinstance(value, date) else str(value).replace("-", "")


def normalize_efinance_columns(df: pd.DataFrame) -> pd.DataFrame:
    work = df.copy()
    if "日期" not in work.columns:
        for column in work.columns:
            if str(column).endswith("日期") or "日期" in str(column):
                work.rename(columns={column: "日期"}, inplace=True)
                break
    for standard in STOCK_HIST_COLUMNS:
        _rename_prefixed_column(work, standard)
    for column in ["日期", "开盘", "最高", "最低", "收盘", "成交量", "成交额", "涨跌幅"]:
        if column not in work.columns:
            raise RuntimeError(f"efinance missing column {column}")
    for column in ["换手率", "振幅"]:
        if column not in work.columns:
            work = work.assign(**{column: pd.NA})
    work["日期"] = pd.to_datetime(work["日期"]).dt.strftime("%Y-%m-%d")
    return work[list(STOCK_HIST_COLUMNS)].copy()


def _rename_prefixed_column(df: pd.DataFrame, standard: str) -> None:
    if standard in df.columns:
        return
    for column in df.columns:
        if str(column).startswith(standard):
            df.rename(columns={column: standard}, inplace=True)
            return
