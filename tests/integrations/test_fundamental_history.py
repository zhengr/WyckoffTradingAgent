from __future__ import annotations

from datetime import date

import pandas as pd

from integrations import fundamental_history as fh
from integrations import tushare_fundamentals as tf


def test_fetch_trims_fields_and_old_records(monkeypatch) -> None:
    def fake_history_map(symbols):
        assert list(symbols) == ["600519", "000001"]
        return {
            "600519": [
                {"announce_date": "2024-04-26", "period_end": "2024-03-31", "roe": 9.0, "eps_basic": 1.0},
                {"announce_date": "2018-04-26", "period_end": "2018-03-31", "roe": 8.0},
                {"announce_date": None, "period_end": "2024-06-30", "roe": 7.0},
            ],
            "000001": [],
        }

    monkeypatch.setattr("integrations.tushare_fundamentals.fetch_history_map", fake_history_map)
    out = fh.fetch_financial_history("ignored-key", ["600519", "000001"], since=date(2024, 6, 1))
    assert list(out) == ["600519"]
    assert out["600519"] == [
        {
            key: {"announce_date": "2024-04-26", "period_end": "2024-03-31", "roe": 9.0}.get(key)
            for key in fh.HISTORY_FIELDS
        }
    ]


def test_fetch_returns_empty_dict_without_tushare_token(monkeypatch) -> None:
    monkeypatch.setattr("integrations.tushare_client.get_pro", lambda: None)
    tf._HISTORY_CACHE.clear()
    out = fh.fetch_financial_history("ignored-key", ["600519"], since=date(2024, 6, 1))
    assert out == {}


class _FakePro:
    ROWS = {
        "600519.SH": [
            {"ann_date": "20180426", "end_date": "20171231", "roe": 8.0},
            {"ann_date": "20240426", "end_date": "20231231", "roe": 9.0},
        ],
        "920001.BJ": [
            {"ann_date": "20250430", "end_date": "20250331", "roe": 6.3, "debt_to_assets": 40.0},
        ],
    }

    def __init__(self) -> None:
        self.requests: list[dict] = []

    def fina_indicator(self, **kwargs):
        self.requests.append(kwargs)
        return pd.DataFrame(self.ROWS.get(kwargs["ts_code"], []))


def test_history_map_renames_fields_and_uses_board_suffix(monkeypatch) -> None:
    pro = _FakePro()
    monkeypatch.setattr("integrations.tushare_client.get_pro", lambda: pro)
    tf._HISTORY_CACHE.clear()
    try:
        out = tf.fetch_history_map(["600519", "920001"])
    finally:
        tf._HISTORY_CACHE.clear()

    assert sorted(out) == ["600519", "920001"]
    assert [r["roe"] for r in out["600519"]] == [8.0, 9.0]
    assert out["600519"][-1]["announce_date"] == "2024-04-26"
    assert out["600519"][-1]["period_end"] == "2023-12-31"
    assert out["920001"][0]["debt_to_asset_ratio"] == 40.0
    ts_codes = {req["ts_code"] for req in pro.requests}
    assert ts_codes == {"600519.SH", "920001.BJ"}
    assert all(req["fields"] == tf.FINA_FIELDS for req in pro.requests)


def test_latest_map_picks_newest_announce_date(monkeypatch) -> None:
    pro = _FakePro()
    monkeypatch.setattr("integrations.tushare_client.get_pro", lambda: pro)
    tf._HISTORY_CACHE.clear()
    try:
        latest = tf.fetch_latest_financial_map(["600519", "920001"])
    finally:
        tf._HISTORY_CACHE.clear()

    assert sorted(latest) == ["600519", "920001"]
    assert latest["600519"]["roe"] == 9.0
    assert latest["600519"]["announce_date"] == "2024-04-26"
    assert latest["920001"]["roe"] == 6.3


def test_to_ts_code_covers_all_boards() -> None:
    assert tf.to_ts_code("600519") == "600519.SH"
    assert tf.to_ts_code("000001") == "000001.SZ"  # 000001 -> .SZ
    assert tf.to_ts_code("300502") == "300502.SZ"
    assert tf.to_ts_code("920001") == "920001.BJ"
    assert tf.to_ts_code("830799") == "830799.BJ"
    assert tf.to_ts_code("430139") == "430139.BJ"
    assert tf.to_ts_code("688001") == "688001.SH"
    assert tf.to_ts_code("510300.SH") == "510300.SH"
