from __future__ import annotations

import pandas as pd


def test_get_market_history_returns_usable_digest(monkeypatch):
    import agents.market_tools as mt

    calls = []

    def _fake_fetch(symbol: str, days: int, tool_context):
        calls.append((symbol, days))
        return (
            pd.DataFrame(
                [
                    {"date": "2026-01-02", "open": 100, "high": 103, "low": 99, "close": 100, "volume": 1000},
                    {"date": "2026-01-03", "open": 102, "high": 106, "low": 101, "close": 105, "volume": 1300},
                    {"date": "2026-01-04", "open": 105, "high": 105, "low": 100, "close": 101, "volume": 1600},
                ]
            ),
            "stock_hist",
            [],
        )

    monkeypatch.setattr(mt, "fetch_market_history_frame", _fake_fetch)

    result = mt.get_market_history(days=3, index="上证")

    assert result["ok"] is True
    assert result["source"] == "stock_hist"
    assert result["index"]["symbol"] == "000001.SH"
    assert result["returned_days"] == 3
    assert result["summary"]["period_return_pct"] == 1.0
    assert result["rows"][-1]["date"] == "2026-01-04"
    assert calls[0][0] == "000001.SH"
