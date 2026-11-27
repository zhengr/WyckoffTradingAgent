from __future__ import annotations

"""腾讯数据源北交所分支：fqkline 只返回当天，历史日线走东财 push2his。"""

from integrations import data_source_tencent as tencent


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _em_payload() -> dict:
    return {
        "rc": 0,
        "data": {
            "code": "920029",
            "klines": [
                "2026-11-24,25.0,24.8,25.2,24.7,10,5000000",
                "2026-11-25,24.8,24.66,25.78,24.40,6485,16000000",
                "2026-11-26,24.9,25.0,25.53,24.65,5930,14800000",
            ],
        },
    }


def test_bse_kline_falls_back_to_eastmoney_push2his(monkeypatch):
    calls = []

    def fake_get(url, params=None, headers=None, timeout=None):
        calls.append(url)
        assert "push2his.eastmoney.com" in url
        assert params["secid"] == "0.920029"
        assert params["klt"] == "101"
        assert params["fqt"] == "1"  # qfq -> 前复权
        return _Resp(_em_payload())

    monkeypatch.setattr(tencent.requests, "get", fake_get)

    df = tencent.fetch_stock_tencent("920029", "20261124", "20261126", "qfq")

    assert calls, "BSE must use eastmoney push2his"
    assert len(df) == 3
    assert list(df["日期"]) == ["2026-11-24", "2026-11-25", "2026-11-26"]
    # push2his 与腾讯一样，volume 单位是手，统一转成股
    assert float(df["成交量"].iloc[-1]) == 593000.0  # 5930 手 * 100
    # 成交额来自 f57
    assert float(df["成交额"].iloc[-1]) == 14800000.0


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
