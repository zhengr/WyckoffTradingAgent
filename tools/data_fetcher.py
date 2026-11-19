"""OHLCV fetch facade.

This module keeps the public batch-fetch API stable while concrete fetching
strategies live in dedicated modules.
"""

from __future__ import annotations

import logging

import pandas as pd

import tools.ohlcv_fallback_fetcher as ohlcv_fallback_fetcher
from core.hist_dates import latest_trade_date_from_hist as latest_trade_date_from_hist

logger = logging.getLogger(__name__)


def fetch_all_ohlcv(
    symbols: list[str],
    window,
    *,
    enforce_target_trade_date: bool = False,
    batch_size: int = ohlcv_fallback_fetcher.BATCH_SIZE,
    max_workers: int = ohlcv_fallback_fetcher.MAX_WORKERS,
    batch_timeout: int = ohlcv_fallback_fetcher.BATCH_TIMEOUT,
    batch_sleep: float = ohlcv_fallback_fetcher.BATCH_SLEEP,
    executor_mode: str = ohlcv_fallback_fetcher.EXECUTOR_MODE,
    direct_source: bool = False,
    runtime_config: ohlcv_fallback_fetcher.FetchRuntimeConfig | None = None,
) -> tuple[dict[str, pd.DataFrame], dict[str, int | float]]:
    """Fetch daily OHLCV for every symbol through the per-symbol fallback chain."""
    df_map, stats = ohlcv_fallback_fetcher.fetch_ohlcv_fallback(
        symbols=symbols,
        window=window,
        enforce_target_trade_date=enforce_target_trade_date,
        batch_size=batch_size,
        max_workers=max_workers,
        batch_timeout=batch_timeout,
        batch_sleep=batch_sleep,
        executor_mode=executor_mode,
        direct_source=direct_source,
        runtime_config=runtime_config,
    )
    return _guard_ohlcv(_annotate_result(df_map, symbols, stats, window))


def _guard_ohlcv(result: tuple[dict[str, pd.DataFrame], dict]) -> tuple[dict[str, pd.DataFrame], dict]:
    from core.ohlc_guard import sanitize_ohlcv_map

    df_map, stats = result
    return sanitize_ohlcv_map(df_map, stats)


def _annotate_result(
    df_map: dict[str, pd.DataFrame],
    symbols: list[str],
    stats: dict[str, int | float],
    window,
) -> tuple[dict[str, pd.DataFrame], dict[str, int | float]]:
    """Split missing symbols into suspended (excluded) and genuine fetch failures."""
    out_stats = dict(stats)
    missing = [symbol for symbol in symbols if symbol not in df_map]
    suspended = _suspended_symbols(window.end_trade_date)
    out_stats["suspended_symbols"] = sorted(symbol for symbol in missing if symbol in suspended)
    out_stats["raw_fetch_missing"] = max(len(symbols) - len(df_map), 0)
    out_stats["excluded_non_trading"] = len(out_stats["suspended_symbols"])
    out_stats["fetch_ok"] = len(df_map)
    out_stats["fetch_fail"] = len([symbol for symbol in symbols if symbol not in df_map and symbol not in suspended])
    return df_map, out_stats


def _suspended_symbols(trade_date) -> set[str]:
    try:
        from integrations.market_metadata import fetch_suspended_symbols

        return fetch_suspended_symbols(trade_date)
    except Exception as exc:
        logger.warning("suspension lookup failed; retrying all missing symbols: %s", exc)
        return set()
