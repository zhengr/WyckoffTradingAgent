from __future__ import annotations

import sys
import types
from datetime import date

import pytest

from workflows import backtest_intraday


def _install_fake_minute_module(monkeypatch: pytest.MonkeyPatch, fetcher) -> None:
    """注入假的 integrations.data_source_minute，避免依赖真实 provider 模块是否已落地。"""
    module = types.ModuleType("integrations.data_source_minute")
    module.intraday_entry_price_fetcher = lambda: fetcher
    monkeypatch.setitem(sys.modules, "integrations.data_source_minute", module)


def test_minute_entry_price_fetcher_uses_minute_provider_without_api_key(monkeypatch: pytest.MonkeyPatch):
    calls = []

    def fetcher(code, day, entry_time, cache):
        calls.append({"code": code, "day": day, "entry_time": entry_time})
        return 10.29, f"minute_1m_{entry_time}"

    _install_fake_minute_module(monkeypatch, fetcher)

    f = backtest_intraday.minute_entry_price_fetcher_from_env()
    assert f is not None

    price, source = f("000001", date(2026, 7, 3), "14:55", {})

    assert price == pytest.approx(10.29)
    assert source == "minute_1m_14:55"
    assert calls == [{"code": "000001", "day": date(2026, 7, 3), "entry_time": "14:55"}]


def test_minute_entry_price_fetcher_returns_none_when_minute_module_missing(monkeypatch: pytest.MonkeyPatch):
    # sys.modules 置 None 会让 import 抛 ImportError，模拟 provider 模块尚未落地
    monkeypatch.setitem(sys.modules, "integrations.data_source_minute", None)

    assert backtest_intraday.minute_entry_price_fetcher_from_env() is None
