from __future__ import annotations

import json
import sys
from datetime import datetime
from io import StringIO
from zoneinfo import ZoneInfo

import pandas as pd

from scripts import a_share_1455_quote_snapshot as snapshot_module
from scripts.a_share_1455_quote_snapshot import fetch_snapshot

_BEIJING = ZoneInfo("Asia/Shanghai")
_NOW = datetime(2026, 9, 29, 14, 55, 30, tzinfo=_BEIJING)


def _row(index: int, *, price: float = 10, date: str = "20260929", name: str | None = None) -> dict:
    return {
        "代码": f"{index:06d}",
        "名称": name or f"公司{index}",
        "最新价": price,
        "昨收": 10.0,
        "成交额": 1_000_000 + index,
        "涨跌幅": (price / 10 - 1) * 100,
        "date": date,
    }


def _frame(rows: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(rows)


def test_full_pool_from_one_spot_fetch_has_compact_first_output(monkeypatch, capsys):
    rows = [_row(index, price=9 if index < 30 else 10) for index in range(5300)]
    calls = []

    def fake_fetch():
        calls.append(1)
        return _frame(rows)

    monkeypatch.setattr(snapshot_module, "fetch_spot_dataframe", fake_fetch)
    summary, candidates = fetch_snapshot(now=_NOW)

    assert len(calls) == 1
    assert summary["ok"] is True
    assert summary["candidate_count"] == 30
    assert summary["coverage"] == 5300
    assert summary["valid_quote_count"] == 5300
    assert summary["data_basis"] == "tdx_post_close_prior_session"
    assert summary["candidate_count_basis"] == "provisional_price_screen_pending_corporate_action_check"
    assert summary["industry_counts"] == {"unmapped": 30}
    assert len(summary["candidates"]) == 20
    assert len(candidates) == 30
    assert len(json.dumps(summary, ensure_ascii=False).encode()) < 10_000


def test_spot_fetch_error_is_reported_without_secrets(monkeypatch):
    def fake_fetch():
        raise RuntimeError("private-endpoint-down")

    monkeypatch.setattr(snapshot_module, "fetch_spot_dataframe", fake_fetch)
    summary, candidates = fetch_snapshot(now=_NOW)

    assert candidates == []
    assert summary["ok"] is False
    assert summary["failure"] == "SPOT_FETCH_ERROR"
    assert summary["exception_type"] == "RuntimeError"
    assert "private-endpoint-down" not in json.dumps(summary)


def test_partial_or_duplicate_pool_is_not_accepted():
    rows = [_row(index) for index in range(5299)] + [_row(0)]
    summary, _ = fetch_snapshot(now=_NOW, spot_df=_frame(rows))

    assert summary["ok"] is False
    assert summary["duplicate_count"] == 1
    assert summary["failure"] == "DATA_INCOMPLETE"


def test_old_illiquid_candidate_does_not_stale_the_post_close_market():
    rows = [_row(index) for index in range(5300)]
    rows[0] = _row(0, price=9, date="20260928")
    summary, candidates = fetch_snapshot(now=_NOW, spot_df=_frame(rows))

    assert summary["ok"] is True
    assert summary["candidates"][0]["symbol"] == "000000.SZ"
    assert summary["candidates"][0]["timestamp"] == "2026-09-28T15:00:00+08:00"
    assert candidates[0]["needs_recheck"] is True
    assert candidates[0]["age_seconds"] > 0


def test_vendor_pct_disagreement_requires_recheck():
    rows = [_row(index) for index in range(5300)]
    rows[0] = _row(0, price=9)
    rows[0]["涨跌幅"] = -1
    summary, candidates = fetch_snapshot(now=_NOW, spot_df=_frame(rows))

    assert summary["quote_pct_mismatch_count"] == 1
    assert candidates[0]["needs_recheck"] is True


def test_malformed_payload_cannot_look_like_zero_candidates():
    summary, candidates = fetch_snapshot(now=_NOW, spot_df={"rows": []})

    assert summary["ok"] is False
    assert summary["failure"] == "INVALID_PAYLOAD"
    assert candidates == []


def test_small_pool_fails_coverage_check_even_without_duplicates():
    summary, _ = fetch_snapshot(now=_NOW, spot_df=_frame([_row(index) for index in range(100)]))

    assert summary["failure"] == "DATA_INCOMPLETE"
    assert summary["coverage"] == 100


def test_malformed_quotes_cannot_fill_the_coverage_floor():
    rows = [_row(index) for index in range(5200)]
    rows[0]["最新价"] = None
    summary, _ = fetch_snapshot(now=_NOW, spot_df=_frame(rows))

    assert summary["coverage"] == 5200
    assert summary["valid_quote_count"] == 5199
    assert summary["failure"] == "DATA_INCOMPLETE"


def test_non_equity_row_is_not_a_deep_drop_candidate():
    rows = [_row(index) for index in range(5301)]
    rows[0]["代码"] = "51ETF0"
    rows[0]["最新价"] = 9
    summary, candidates = fetch_snapshot(now=_NOW, spot_df=_frame(rows))

    assert summary["ok"] is True
    assert summary["coverage"] == 5300
    assert summary["valid_quote_count"] == 5300
    assert summary["null_count"] == 1
    assert candidates == []


def test_intraday_basis_uses_fetch_time_and_marks_live(monkeypatch):
    rows = [_row(index, price=9 if index == 0 else 10) for index in range(5300)]
    for row in rows:
        row.pop("date")
    summary, _ = fetch_snapshot(now=_NOW, spot_df=_frame(rows))

    assert summary["ok"] is True
    assert summary["data_basis"] == "eastmoney_intraday_spot"
    assert summary["market_state"] == "live"
    assert summary["active_latest_time"] == _NOW.isoformat(timespec="seconds")


def test_interactive_pages_keep_full_candidates_in_memory(monkeypatch, capsys):
    candidates = [{"symbol": f"{index:06d}.SZ"} for index in range(25)]
    summary = {"ok": True, "candidates": candidates[:20], "candidate_count": 25}
    monkeypatch.setattr(snapshot_module, "fetch_snapshot", lambda: (summary, candidates))
    monkeypatch.setattr(sys, "stdin", StringIO("page 1\nquit\n"))
    monkeypatch.setattr(sys, "argv", ["snapshot", "--interactive"])

    assert snapshot_module.main() == 0

    first, second = (json.loads(line) for line in capsys.readouterr().out.splitlines())
    assert len(first["candidates"]) == 20
    assert second["page"] == 1
    assert len(second["candidates"]) == 5
