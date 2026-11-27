from __future__ import annotations

"""腾讯数据源北交所分支：fqkline 只返回当天，bj 直接抛异常落到 sina。"""

import pytest

from integrations import data_source_sina
from integrations import data_source_tencent as tencent


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def test_bse_deferred_to_sina_via_raise():
    # tencent 对 bj 必须抛异常，让源链落到 sina
    with pytest.raises(RuntimeError, match="defer to sina"):
        tencent._request_kline("bj920029", "qfq", "2026-11-01", "2026-11-26", 100)


def test_sina_maps_bse_prefixes_to_bj():
    assert data_source_sina._sina_symbol("920029") == "bj920029"
    assert data_source_sina._sina_symbol("430047") == "bj430047"
    assert data_source_sina._sina_symbol("830799") == "bj830799"
    assert data_source_sina._sina_symbol("600519") == "sh600519"
    assert data_source_sina._sina_symbol("000001") == "sz000001"


def test_a_share_kline_keeps_tencent_and_amount_na(monkeypatch):
    def fake_get(url, params=None, headers=None, timeout=None):
        assert "fqkline" in url
        assert params["param"].startswith("sh600519,day,")
        return _Resp(
            {
                "code": 0,
                "data": {
                    "sh600519": {
                        "qfqday": [
                            ["2026-11-25", "1300.0", "1310.0", "1315.0", "1295.0", "38500.0"],
                            ["2026-11-26", "1310.0", "1320.0", "1325.0", "1305.0", "40000.0"],
                        ]
                    }
                },
            }
        )

    monkeypatch.setattr(tencent.requests, "get", fake_get)

    df = tencent.fetch_stock_tencent("600519", "20261125", "20261126", "qfq")

    assert len(df) == 2
    assert df["成交额"].isna().all()  # 腾讯 A 股无成交额，保持 NA
    assert float(df["成交量"].iloc[-1]) == 40000.0 * 100.0  # 手转股


def test_tencent_trade_calendar_from_index_kline(monkeypatch):
    import requests as _rq

    from integrations import fetch_a_share_csv as fasc

    class _R:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "code": 0,
                "data": {
                    "sh000001": {
                        "qfqday": [
                            ["2026-11-25", "1", "2", "3", "2", "100"],
                            ["2026-11-26", "1", "2", "3", "2", "100"],
                        ]
                    }
                },
            }

    monkeypatch.setattr(_rq, "get", lambda *a, **k: _R())
    dates = fasc._fetch_trade_dates_tencent()
    assert [d.isoformat() for d in dates] == ["2026-11-25", "2026-11-26"]
