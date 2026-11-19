"""腾讯 / 新浪日K provider 的列归一化测试（不发真实网络请求）。"""

from __future__ import annotations

import pandas as pd
import pytest

import integrations.data_source_sina as sina_provider
import integrations.data_source_tencent as tencent_provider
from integrations.data_source_format import STOCK_HIST_COLUMNS


class _FakeResponse:
    def __init__(self, payload: object) -> None:
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> object:
        return self._payload


def _tencent_qfqday() -> dict:
    return {
        "code": 0,
        "data": {
            "sh600519": {
                "qfqday": [
                    ["2026-11-17", "1450.000", "1456.660", "1457.000", "1445.000", "20000.000"],
                    ["2026-11-18", "1450.000", "1442.660", "1456.000", "1431.700", "29847.000"],
                ]
            }
        },
    }


def test_tencent_provider_normalizes_rows_to_standard_columns(monkeypatch) -> None:
    captured: dict = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["url"] = url
        captured["params"] = params
        return _FakeResponse(_tencent_qfqday())

    monkeypatch.setattr(tencent_provider.requests, "get", fake_get)

    out = tencent_provider.fetch_stock_tencent("600519", "20261101", "20261118", "qfq")

    assert captured["params"]["param"].startswith("sh600519,day,2026-11-01,2026-11-18")
    assert tuple(out.columns) == STOCK_HIST_COLUMNS
    assert out.iloc[-1]["日期"] == "2026-11-18"
    assert float(out.iloc[-1]["收盘"]) == pytest.approx(1442.66)
    # 腾讯 volume 单位是手，转成股
    assert float(out.iloc[-1]["成交量"]) == pytest.approx(29847.0 * 100)
    assert out.iloc[-1]["成交额"] is pd.NA or pd.isna(out.iloc[-1]["成交额"])


def test_tencent_provider_rejects_empty_range(monkeypatch) -> None:
    empty = {"code": 0, "data": {"sh600519": {"qfqday": []}}}
    monkeypatch.setattr(tencent_provider.requests, "get", lambda *a, **k: _FakeResponse(empty))

    with pytest.raises(RuntimeError, match="tencent no kline rows"):
        tencent_provider.fetch_stock_tencent("600519", "20261101", "20261118", "qfq")


def test_sina_provider_normalizes_rows_to_standard_columns(monkeypatch) -> None:
    rows = [
        {"day": "2026-11-17", "open": "1450.000", "high": "1457.000", "low": "1445.000", "close": "1456.660", "volume": "2000000"},
        {"day": "2026-11-18", "open": "1450.000", "high": "1456.000", "low": "1431.700", "close": "1442.660", "volume": "2984695"},
    ]
    captured: dict = {}

    def fake_get(url, params=None, headers=None, timeout=None):
        captured["params"] = params
        return _FakeResponse(rows)

    monkeypatch.setattr(sina_provider.requests, "get", fake_get)

    out = sina_provider.fetch_stock_sina("600519", "20261101", "20261118", "qfq")

    assert captured["params"]["symbol"] == "sh600519"
    assert tuple(out.columns) == STOCK_HIST_COLUMNS
    assert out.iloc[-1]["日期"] == "2026-11-18"
    assert float(out.iloc[-1]["收盘"]) == pytest.approx(1442.66)
    assert float(out.iloc[-1]["成交量"]) == pytest.approx(2984695.0)
