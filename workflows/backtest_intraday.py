"""Intraday entry-price adapters for backtest workflows."""

from __future__ import annotations

import logging

from core.backtest_execution import IntradayPriceFetcher

logger = logging.getLogger(__name__)


def minute_entry_price_fetcher_from_env() -> IntradayPriceFetcher | None:
    """历史分钟线入场价 fetcher；不需要额外凭据。

    历史交易日的分钟线由 integrations.data_source_minute 提供
    （intraday_entry_price_fetcher，无需 key，可取任意过去交易日）。
    数据源不可用时返回 None，回测侧 tail_1455 回退到日线收盘价口径。
    """
    try:
        from integrations.data_source_minute import intraday_entry_price_fetcher
    except ImportError as exc:
        logger.warning("minute data source unavailable, tail_1455 falls back to daily close: %s", exc)
        return None
    return intraday_entry_price_fetcher()


# Backward-compatible alias：旧名保留，供外部调用方平滑过渡。
