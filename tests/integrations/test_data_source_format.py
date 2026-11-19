from __future__ import annotations

import pandas as pd

from integrations.data_source_format import (
    STOCK_HIST_COLUMNS,
    hist_date_text,
    normalize_cn_exchange_code,
    normalize_efinance_columns,
    to_ts_code,
)


def test_to_ts_code_resolves_cn_exchange_suffix() -> None:
    assert to_ts_code("600519") == "600519.SH"
    assert to_ts_code("000001") == "000001.SZ"
    assert to_ts_code("600519.SH") == "600519.SH"


def test_normalize_efinance_columns_returns_standard_stock_hist_columns() -> None:
    raw = pd.DataFrame(
        {
            "股票日期": ["2026-06-01"],
            "开盘价": [10.0],
            "最高价": [10.5],
            "最低价": [9.8],
            "收盘价": [10.2],
            "成交量": [1000],
            "成交额": [10200],
            "涨跌幅": [2.0],
        }
    )

    out = normalize_efinance_columns(raw)

    assert tuple(out.columns) == STOCK_HIST_COLUMNS
    assert out.iloc[0]["日期"] == "2026-06-01"
    assert pd.isna(out.iloc[0]["换手率"])


def test_normalize_cn_exchange_code_keeps_existing_suffix() -> None:
    assert normalize_cn_exchange_code("600519") == "600519.SH"
    assert normalize_cn_exchange_code("000001") == "000001.SZ"
    assert normalize_cn_exchange_code("830001") == "830001.BJ"
    assert normalize_cn_exchange_code("600519.SH") == "600519.SH"


def test_hist_date_text_normalizes_dates() -> None:
    assert hist_date_text("2026-06-02") == "20260602"
