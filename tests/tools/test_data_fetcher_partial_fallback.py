from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pandas as pd

from tools import data_fetcher


def test_missing_symbols_are_reported_and_suspended_excluded(monkeypatch) -> None:
    frame = pd.DataFrame({"date": ["2026-07-15"], "close": [10.0]})
    captured = {}

    def fake_fallback(**kwargs):
        captured.update(kwargs)
        return {"000001": frame, "000002": frame}, {"fetch_ok": 2, "fetch_fail": 1}

    monkeypatch.setattr(data_fetcher.ohlcv_fallback_fetcher, "fetch_ohlcv_fallback", fake_fallback)
    monkeypatch.setattr(data_fetcher, "_suspended_symbols", lambda _day: {"000003"})
    window = SimpleNamespace(start_trade_date=date(2026, 1, 1), end_trade_date=date(2026, 7, 15))

    result, stats = data_fetcher.fetch_all_ohlcv(["000001", "000002", "000003"], window)

    assert set(result) == {"000001", "000002"}
    assert captured["symbols"] == ["000001", "000002", "000003"]
    assert stats["suspended_symbols"] == ["000003"]
    assert stats["raw_fetch_missing"] == 1
    assert stats["excluded_non_trading"] == 1
    assert stats["fetch_ok"] == 2
    assert stats["fetch_fail"] == 0
