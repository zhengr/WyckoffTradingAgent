"""Market-data loading for single-symbol funnel diagnosis."""

from __future__ import annotations

from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

import pandas as pd

from core.wyckoff_engine import normalize_hist_from_fetch
from integrations.data_source import fetch_stock_hist
from integrations.data_source_hk_us import fetch_stock_hk_us
from integrations.fetch_a_share_csv import get_stocks_by_board
from integrations.index_data_source import fetch_index_hist
from integrations.market_metadata import fetch_market_cap_map, fetch_sector_map
from tools.market_universe_meta import load_symbol_name_map


@dataclass(frozen=True)
class SingleSymbolContextData:
    name_map: dict[str, str]
    market_cap_map: dict[str, float]
    sector_map: dict[str, str]
    bench_df: pd.DataFrame | None


def fetch_symbol_history(spec: Any, start: date, end: date, trading_days: int) -> pd.DataFrame:
    fetch_start = start - timedelta(days=max(trading_days * 3, 760))
    if spec.market == "cn":
        raw = fetch_stock_hist(spec.symbol, fetch_start, end, adjust="qfq")
    else:
        raw = fetch_stock_hk_us(spec.symbol, fetch_start, end, "qfq")
    return prepare_symbol_history(raw, start, end, trading_days)


def load_symbol_context(
    spec: Any,
    hist: pd.DataFrame,
    start: date,
    end: date,
    log: Callable[[str], None] | None = None,
) -> SingleSymbolContextData:
    name_map = _name_map(spec)
    if spec.market != "cn":
        return SingleSymbolContextData(name_map, {}, {}, None)
    logger = log or (lambda _msg: None)
    return SingleSymbolContextData(
        name_map,
        _safe_fetch_market_cap_map(logger),
        _safe_fetch_sector_map(logger),
        _safe_fetch_benchmark(start, end, hist, logger),
    )


def load_rps_universe_histories(
    spec: Any,
    start: date,
    end: date,
    rps_window: int = 150,
    log: Callable[[str], None] | None = None,
) -> dict[str, pd.DataFrame]:
    if spec.market != "cn":
        return {}
    logger = log or (lambda _msg: None)
    symbols = _rps_symbols(spec)
    if not symbols:
        return {}
    logger(f"[diagnosis] RPS 全市场加载: universe={len(symbols)} symbols")
    fetch_start = start - timedelta(days=max(rps_window * 3, 400))
    out: dict[str, pd.DataFrame] = {}
    with ThreadPoolExecutor(max_workers=8) as executor:
        futures = {executor.submit(_fetch_rps_one, symbol, fetch_start, end, rps_window): symbol for symbol in symbols}
        for future in as_completed(futures):
            frame = future.result()
            if frame is not None:
                out[futures[future]] = frame
    logger(f"[diagnosis] RPS 历史加载完成: fetched={len(out)}/{len(symbols)}")
    return out


def _fetch_rps_one(symbol: str, fetch_start: date, end: date, rps_window: int) -> pd.DataFrame | None:
    try:
        raw = fetch_stock_hist(symbol, fetch_start, end, "qfq")
    except Exception:
        return None
    return _normalized_rps_batch({symbol: raw}, rps_window).get(symbol)


def prepare_symbol_history(raw: pd.DataFrame, start: date, end: date, trading_days: int) -> pd.DataFrame:
    df = normalize_hist_from_fetch(raw)
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.dropna(subset=["date", "open", "high", "low", "close"]).copy()
    df["date_obj"] = pd.to_datetime(df["date"], errors="coerce").dt.date
    df = df.dropna(subset=["date_obj"]).sort_values("date_obj").reset_index(drop=True)
    df["date"] = pd.to_datetime(df["date_obj"]).dt.strftime("%Y-%m-%d")
    first_idx = _first_index_on_or_after(df, start)
    if first_idx is None:
        return pd.DataFrame()
    trim_from = max(first_idx - trading_days, 0)
    return df[(df.index >= trim_from) & (df["date_obj"] <= end)].reset_index(drop=True)


def _name_map(spec: Any) -> dict[str, str]:
    if spec.market in {"hk", "us"}:
        names = load_symbol_name_map((spec.market,))
        return {spec.symbol: names.get(spec.symbol, spec.symbol)}
    return {spec.symbol: spec.symbol}


def _safe_fetch_market_cap_map(log: Callable[[str], None]) -> dict[str, float]:
    try:
        return fetch_market_cap_map()
    except Exception as exc:
        log(f"[diagnosis] 市值映射获取失败，跳过市值精确诊断: {exc}")
        return {}


def _safe_fetch_sector_map(log: Callable[[str], None]) -> dict[str, str]:
    try:
        return fetch_sector_map()
    except Exception as exc:
        log(f"[diagnosis] 行业映射获取失败，跳过行业精确诊断: {exc}")
        return {}


def _safe_fetch_benchmark(
    start: date, end: date, hist: pd.DataFrame, log: Callable[[str], None]
) -> pd.DataFrame | None:
    try:
        bench_start = min(hist["date_obj"]) if not hist.empty else start
        return fetch_index_hist("000001", bench_start, end)
    except Exception as exc:
        log(f"[diagnosis] 大盘基准获取失败，Layer2 相对强弱会降级: {exc}")
        return None


def _rps_symbols(spec: Any) -> list[str]:
    items = get_stocks_by_board("all")
    symbols = [str(item["code"]).strip() for item in items if item.get("code")]
    return [symbol for symbol in symbols if symbol and symbol != spec.symbol]


def _normalized_rps_batch(batch: dict[str, pd.DataFrame], rps_window: int) -> dict[str, pd.DataFrame]:
    out: dict[str, pd.DataFrame] = {}
    for symbol, df in batch.items():
        norm = normalize_hist_from_fetch(df)
        if norm is not None and len(norm) >= rps_window:
            out[symbol] = norm
    return out


def _first_index_on_or_after(df: pd.DataFrame, day: date) -> int | None:
    hits = df.index[df["date_obj"] >= day]
    return int(hits[0]) if len(hits) else None
