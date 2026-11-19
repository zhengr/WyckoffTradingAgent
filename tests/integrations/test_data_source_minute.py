from __future__ import annotations

import pandas as pd
import pytest

import integrations.data_source_minute as minute


class _FakeResponse:
    def __init__(self, payload: dict):
        self._payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self._payload


def test_norm_period_and_unsupported_us() -> None:
    assert minute._norm_period("5m") == "5"
    assert minute._norm_period("60") == "60"
    with pytest.raises(RuntimeError, match="unsupported minute period"):
        minute._norm_period("7")
    with pytest.raises(RuntimeError, match="美股分钟线"):
        minute.fetch_minute_hist("AAPL.US", "5")


def test_cn_minute_uses_akshare_and_normalizes_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = {}

    def _fake_min(**kwargs):
        calls.update(kwargs)
        return pd.DataFrame(
            {
                "时间": ["2026-11-19 09:35:00", "2026-11-19 09:40:00"],
                "开盘": [10.0, 10.1],
                "收盘": [10.1, 10.2],
                "最高": [10.2, 10.3],
                "最低": [9.9, 10.0],
                "成交量": [100, 120],
                "成交额": [101000.0, 122400.0],
                "涨跌幅": [1.0, 0.99],
                "换手率": [0.1, 0.12],
            }
        )

    import akshare as ak

    monkeypatch.setattr(ak, "stock_zh_a_hist_min_em", _fake_min)
    df = minute.fetch_minute_hist("600519", "5m", "2026-11-19 09:30", "2026-11-19 15:00")
    assert calls["period"] == "5"
    assert list(df.columns) == [
        "datetime",
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "pct_chg",
        "turnover",
    ]
    assert str(df.iloc[0]["datetime"].tz) == "Asia/Shanghai"
    assert float(df.iloc[-1]["close"]) == 10.2


def test_hk_minute_uses_tencent_mkline(monkeypatch: pytest.MonkeyPatch) -> None:
    payload = {
        "code": 0,
        "data": {
            "hk00700": {
                "m5": [
                    ["2026/11/19 09:35", "600", "605", "608", "598", "100"],
                    ["2026/11/19 09:40", "605", "607", "610", "600", "120"],
                ]
            }
        },
    }
    monkeypatch.setattr(minute.requests, "get", lambda *a, **k: _FakeResponse(payload))
    df = minute.fetch_minute_hist("00700.HK", "5m")
    assert len(df) == 2
    assert float(df.iloc[-1]["close"]) == 607.0
    assert pd.isna(df.iloc[-1]["amount"])


def test_intraday_entry_price_fetcher_uses_minute_history(monkeypatch: pytest.MonkeyPatch) -> None:
    from datetime import date

    frame = pd.DataFrame(
        {
            "datetime": pd.to_datetime(["2026-11-19 14:54", "2026-11-19 14:55"]).tz_localize("Asia/Shanghai"),
            "close": [10.0, 10.5],
            "date": ["2026-11-19", "2026-11-19"],
            "open": [10.0, 10.5],
            "high": [10.0, 10.5],
            "low": [10.0, 10.5],
            "volume": [1, 1],
            "amount": [10.0, 10.5],
        }
    )
    monkeypatch.setattr(minute, "fetch_minute_hist", lambda *a, **k: frame)
    fetcher = minute.intraday_entry_price_fetcher()
    price, tag = fetcher("600519", date(2026, 11, 19), "14:55", {})
    assert price == 10.5
    assert tag == "minute_1m_14:55"
