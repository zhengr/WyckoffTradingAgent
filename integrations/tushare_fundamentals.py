"""Tushare ``fina_indicator`` 适配层，提供批量财务指标与 PIT 历史。

字段映射：
* ``ann_date`` -> ``announce_date``，``end_date`` -> ``period_end``；
* 其余字段统一转成 ``core.fundamental_overlay.FIELD_ALIASES`` 里的仓库主字段名
  （``netprofit_yoy`` -> ``net_income_yoy``、``or_yoy`` -> ``revenue_yoy`` 等）。

PIT 语义：适配层忠实透出 ``announce_date``（YYYY-MM-DD），不做任何按报告期近似；
记录只能在 announce_date 严格早于信号日时使用，由 core.asof_cut 的消费侧裁切保证。
未配置 Tushare token 时所有查询返回空结构，不抛异常。
"""

from __future__ import annotations

import logging
import math
from collections.abc import Mapping
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime
from typing import Any

from core.candidate_metadata import code6

logger = logging.getLogger(__name__)

FINA_FIELDS = "ann_date,end_date,roe,roe_diluted,netprofit_yoy,or_yoy,grossprofit_margin,debt_to_assets,ocf_to_or"

COLUMN_ALIASES = {
    "roe": "roe",
    "roe_diluted": "roe_diluted",
    "netprofit_yoy": "net_income_yoy",
    "or_yoy": "revenue_yoy",
    "grossprofit_margin": "gross_margin",
    "debt_to_assets": "debt_to_asset_ratio",
    "ocf_to_or": "operating_cash_to_revenue",
}
DATE_RENAMES = {"ann_date": "announce_date", "end_date": "period_end"}

_HISTORY_CACHE: dict[str, list[dict[str, Any]]] = {}


def to_ts_code(symbol: str) -> str:
    """六位代码转 Tushare 代码；北交所 4/8/9 开头用 .BJ（不能猜成 .SZ）。"""
    code = str(symbol or "").strip()
    if "." in code:
        return code
    digits = "".join(ch for ch in code if ch.isdigit())
    if len(digits) != 6:
        return code
    if digits.startswith(("4", "8", "9")):
        return f"{digits}.BJ"
    return f"{digits}.SH" if digits.startswith(("5", "6")) else f"{digits}.SZ"


def normalize_record(row: Mapping[str, Any]) -> dict[str, Any]:
    """一条 Tushare fina_indicator 行 -> 仓库字段名记录（日期统一 YYYY-MM-DD）。"""
    record: dict[str, Any] = {}
    for source, target in {**DATE_RENAMES, **COLUMN_ALIASES}.items():
        if source not in row:
            continue
        value = row[source]
        if isinstance(value, float) and not math.isfinite(value):
            value = None
        record[target] = value
    record["announce_date"] = _iso_date(record.get("announce_date"))
    record["period_end"] = _iso_date(record.get("period_end"))
    return record


def fetch_symbol_history(
    symbol: str, *, start_date: str | None = None, end_date: str | None = None
) -> list[dict[str, Any]]:
    """逐只查询 fina_indicator，返回按 announce_date 升序排列的仓库字段名记录。"""
    from integrations.tushare_client import get_pro

    pro = get_pro()
    if pro is None:
        return []
    ts_code = to_ts_code(symbol)
    use_cache = not start_date and not end_date
    if use_cache and ts_code in _HISTORY_CACHE:
        return [dict(row) for row in _HISTORY_CACHE[ts_code]]

    kwargs: dict[str, Any] = {"ts_code": ts_code, "fields": FINA_FIELDS}
    if start_date:
        kwargs["start_date"] = _compact_date(start_date)
    if end_date:
        kwargs["end_date"] = _compact_date(end_date)
    try:
        frame = pro.fina_indicator(**kwargs)
    except Exception as exc:
        logger.warning("fina_indicator 查询失败 %s: %s", ts_code, exc)
        return []

    records = [normalize_record(row) for row in _rows(frame)]
    records = [row for row in records if row.get("announce_date")]
    records.sort(key=lambda row: (row["announce_date"], str(row.get("period_end") or "")))
    if use_cache:
        _HISTORY_CACHE[ts_code] = [dict(row) for row in records]
    return records


def fetch_history_map(symbols: list[str], *, max_workers: int = 8) -> dict[str, list[dict[str, Any]]]:
    """按六位代码返回逐只历史记录；无 token / 全部失败时返回空 dict。"""
    targets = {code: symbol for symbol in symbols if (code := code6(symbol))}
    if not targets:
        return {}
    out: dict[str, list[dict[str, Any]]] = {}
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as pool:
        futures = {pool.submit(fetch_symbol_history, symbol): code for code, symbol in targets.items()}
        for future in as_completed(futures):
            code = futures[future]
            try:
                records = future.result()
            except Exception as exc:
                logger.warning("fina_indicator 历史查询失败 %s: %s", code, exc)
                continue
            if records:
                out[code] = records
    return out


def fetch_latest_financial_map(symbols: list[str], *, max_workers: int = 8) -> dict[str, dict[str, Any]]:
    """按六位代码返回最新公告记录（announce_date 最大者）。"""
    history = fetch_history_map(symbols, max_workers=max_workers)
    return {code: records[-1] for code, records in history.items() if records}


def _rows(frame: Any) -> list[Mapping[str, Any]]:
    if frame is None:
        return []
    if isinstance(frame, list):
        return [row for row in frame if isinstance(row, Mapping)]
    if hasattr(frame, "to_dict"):
        return list(frame.to_dict("records"))
    return []


def _iso_date(value: Any) -> str:
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = str(value or "").strip()
    if not text or text.lower() in {"nan", "nat", "none"}:
        return ""
    if len(text) == 8 and text.isdigit():
        return f"{text[:4]}-{text[4:6]}-{text[6:]}"
    return text[:10]


def _compact_date(value: str | date) -> str:
    return _iso_date(value).replace("-", "")
