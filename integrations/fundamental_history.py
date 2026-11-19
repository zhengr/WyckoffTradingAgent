"""Point-in-time financial history from Tushare ``fina_indicator``, keyed on six-digit code.

The Tushare adapter returns every quarterly record with an ``announce_date``; a record may only
be used on signal dates strictly after that day, since the vendor gives a date without a time.
Records without an announce date are dropped rather than approximated by ``period_end`` — the
report-period end is not when the market learned it.
"""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from core.asof_cut import FINANCIAL_RECORD_MAX_AGE_DAYS

HISTORY_FIELDS = (
    "announce_date",
    "period_end",
    "roe",
    "roe_diluted",
    "debt_to_asset_ratio",
    "operating_cash_to_revenue",
    "gross_margin",
    "net_income_yoy",
    "revenue_yoy",
)


def fetch_financial_history(api_key: str, symbols: list[str], *, since: date) -> dict[str, list[dict[str, Any]]]:
    """Quarterly records announced on or after ``since - FINANCIAL_RECORD_MAX_AGE_DAYS``, trimmed to HISTORY_FIELDS.

    The backtest only ever looks back one staleness window before its first signal date, so
    older rows are not written. Without a Tushare token the result is an empty dict.
    """
    # api_key 只保留签名兼容；实际凭据来自 integrations.tushare_client（TUSHARE_TOKEN）。
    del api_key
    from integrations.tushare_fundamentals import fetch_history_map

    floor = (since - timedelta(days=FINANCIAL_RECORD_MAX_AGE_DAYS)).isoformat()
    raw = fetch_history_map(symbols)
    out: dict[str, list[dict[str, Any]]] = {}
    for code, records in raw.items():
        kept = [
            {key: item.get(key) for key in HISTORY_FIELDS}
            for item in records
            if isinstance(item, dict) and str(item.get("announce_date") or "") >= floor
        ]
        if code and kept:
            out[code] = sorted(kept, key=lambda item: (str(item["announce_date"]), str(item.get("period_end") or "")))
    return out
