from __future__ import annotations

import pandas as pd
import pytest

import integrations.data_source as ds
import integrations.data_source_hk_us as hk_us
from integrations.data_source_format import STOCK_HIST_COLUMNS


def test_normalize_hk_us_symbol() -> None:
    assert hk_us.normalize_hk_us_symbol("hk00700") == "00700.HK"
    assert hk_us.normalize_hk_us_symbol("00700.HK") == "00700.HK"
    assert hk_us.normalize_hk_us_symbol("usAAPL") == "AAPL.US"
    assert hk_us.normalize_hk_us_symbol("600519") == ""
    assert hk_us.is_hk_us_symbol("AAPL") is True
    assert hk_us.is_hk_us_symbol("000001") is False


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_fetch_hk_daily_parses_tencent_rows(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "code": 0,
        "data": {
            "hk00700": {
                "day": [
                    ["2026-11-17", "600", "610", "615", "595", "1000"],
                    ["2026-11-18", "610", "620", "625", "605", "1200"],
                ]
            }
        },
    }
    monkeypatch.setattr(hk_us.requests, "get", lambda *a, **k: _FakeResponse(payload))
    df = hk_us.fetch_stock_hk_us("00700.HK", "20261117", "20261118")
    assert tuple(df.columns) == STOCK_HIST_COLUMNS
    assert df.attrs["source"] == "tencent_hk_us"
    assert list(df["日期"]) == ["2026-11-17", "2026-11-18"]
    assert float(df.iloc[-1]["收盘"]) == 620.0
    assert pd.notna(df.iloc[-1]["涨跌幅"])


def test_fetch_us_daily_uses_qfqday(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "code": 0,
        "data": {
            "usAAPL": {
                "qfqday": [["2026-11-18", "200", "205", "208", "199", "5000"]],
            }
        },
    }
    monkeypatch.setattr(hk_us.requests, "get", lambda *a, **k: _FakeResponse(payload))
    df = hk_us.fetch_stock_hk_us("AAPL.US", "2026-11-18", "2026-11-18", adjust="qfq")
    assert list(df["日期"]) == ["2026-11-18"]
    assert float(df.iloc[0]["收盘"]) == 205.0


def test_fetch_stock_hk_us_routes_hk_us_symbols(monkeypatch: pytest.MonkeyPatch) -> None:
    seen = []

    def _fake(symbol: str, start: str, end: str, adjust: str) -> pd.DataFrame:
        seen.append(symbol)
        return pd.DataFrame(
            [
                {
                    "日期": "2026-11-18",
                    "开盘": 1,
                    "最高": 2,
                    "最低": 0.5,
                    "收盘": 1.5,
                    "成交量": 10,
                    "成交额": pd.NA,
                    "涨跌幅": 1.0,
                    "换手率": pd.NA,
                    "振幅": 1.0,
                }
            ]
        )

    monkeypatch.setattr(hk_us, "fetch_stock_hk_us", _fake)
    out = ds.fetch_stock_hist("00700.HK", "20261117", "20261118")
    assert seen == ["00700.HK"]
    assert out.attrs["source"] == "tencent_hk_us"
