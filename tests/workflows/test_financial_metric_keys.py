"""财务指标 map 的主键契约：供应商后缀只存在于请求/响应边界，map 一律六位代码。"""

from __future__ import annotations

import pandas as pd
import pytest

from core.mainline_engine import _lookup_financial
from integrations import tushare_fundamentals as tf
from workflows.funnel_data import _load_financial_metrics
from workflows.funnel_data_quality import build_funnel_data_quality
from workflows.step3_candidates import _fetch_step3_financial_map


class _FakePro:
    """模拟 tushare pro.fina_indicator：按 ts_code 返回原始字段名的行。"""

    ROWS = {
        "300502.SZ": [{"ann_date": "20250425", "end_date": "20241231", "roe": 14.52, "debt_to_assets": 31.04}],
        "601138.SH": [
            {"ann_date": "20250428", "end_date": "20250331", "roe": 7.0, "debt_to_assets": 50.0},
            {"ann_date": "20250829", "end_date": "20250630", "roe": 8.10, "debt_to_assets": 55.20},
        ],
        "920001.BJ": [{"ann_date": "20250430", "end_date": "20250331", "roe": 6.30, "debt_to_assets": 40.00}],
    }

    def __init__(self) -> None:
        self.requests: list[dict] = []

    def fina_indicator(self, **kwargs) -> pd.DataFrame:
        self.requests.append(kwargs)
        return pd.DataFrame(self.ROWS.get(kwargs["ts_code"], []))


@pytest.fixture
def _fake_tushare(monkeypatch: pytest.MonkeyPatch):
    pro = _FakePro()
    monkeypatch.setattr("integrations.tushare_client.get_pro", lambda: pro)
    monkeypatch.setattr("integrations.tushare_client.has_tushare_token", lambda: True)
    monkeypatch.delenv("FUNNEL_SKIP_FINANCIAL_METRICS", raising=False)
    tf._HISTORY_CACHE.clear()
    yield pro
    tf._HISTORY_CACHE.clear()


def test_funnel_loader_keys_are_six_digit_codes(_fake_tushare: _FakePro) -> None:
    result = _load_financial_metrics(["300502", "601138", "920001"])

    assert sorted(result) == ["300502", "601138", "920001"]
    assert result["300502"]["roe"] == 14.52
    assert result["920001"]["roe"] == 6.30
    assert result["300502"]["announce_date"] == "2025-04-25"
    assert result["300502"]["debt_to_asset_ratio"] == 31.04


def test_step3_loader_keys_are_six_digit_codes(_fake_tushare: _FakePro) -> None:
    result = _fetch_step3_financial_map(["300502", "601138", "920001"])

    assert sorted(result) == ["300502", "601138", "920001"]


def test_loader_requests_use_board_suffix_and_latest_newest_record(_fake_tushare: _FakePro) -> None:
    _load_financial_metrics(["300502", "601138", "920001"])

    ts_codes = {req["ts_code"] for req in _fake_tushare.requests}
    assert ts_codes == {"300502.SZ", "601138.SH", "920001.BJ"}
    assert all(req["fields"] == tf.FINA_FIELDS for req in _fake_tushare.requests)

    result = _load_financial_metrics(["601138"])
    assert result["601138"]["roe"] == 8.10
    assert result["601138"]["announce_date"] == "2025-08-29"


def test_funnel_loader_returns_empty_without_tushare_token(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("integrations.tushare_client.get_pro", lambda: None)
    monkeypatch.setattr("integrations.tushare_client.has_tushare_token", lambda: False)
    monkeypatch.delenv("FUNNEL_SKIP_FINANCIAL_METRICS", raising=False)
    tf._HISTORY_CACHE.clear()

    assert _load_financial_metrics(["300502"]) == {}


def test_coverage_counts_suffixed_vendor_response(_fake_tushare: _FakePro) -> None:
    """回归：供应商后缀只在请求边界出现，map 主键一律六位代码，覆盖率才能正确统计。"""
    symbols = ["300502", "601138"]
    financial_map = _load_financial_metrics(symbols)

    quality = build_funnel_data_quality(
        symbols,
        {sym: pd.DataFrame({"close": [10.0]}) for sym in symbols},
        {sym: 100.0 for sym in symbols},
        financial_map,
        financial_requested=True,
    )

    assert quality["counts"]["financial"] == 2
    assert quality["coverage"]["financial"] == 1.0


@pytest.mark.parametrize("code", ["300502", "601138", "920001", "830799", "430139", "688001"])
def test_mainline_lookup_resolves_every_board(code: str) -> None:
    """北交所 4/8/9 开头此前被猜成 .SH/.SZ，双键兼容对其全部失效。"""
    assert _lookup_financial({code: {"roe": 1.0}}, code) == {"roe": 1.0}
