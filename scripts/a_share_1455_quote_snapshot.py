"""Strict, read-only first quote snapshot for the independent 14:55 A-share study."""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

import pandas as pd

from integrations.spot_snapshot import fetch_spot_dataframe, normalize_spot_symbol

_BEIJING = ZoneInfo("Asia/Shanghai")
_SYMBOL = re.compile(r"^\d{6}$")
_MIN_COVERAGE = 5200
_PAGE_SIZE = 20
_SPOT_BASIS = "eastmoney_intraday_spot"
_TDX_BASIS = "tdx_post_close_prior_session"


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if result == result and abs(result) != float("inf") else None


def _suffix(code: str) -> str:
    if code.startswith(("0", "1", "2", "3")):
        return "SZ"
    if code.startswith(("4", "8", "9")):
        return "BJ"
    return "SH"


def _detect_basis(df: pd.DataFrame) -> str:
    """The tdx post-close package carries a trade date; the EastMoney spot feed does not."""
    return _TDX_BASIS if "date" in df.columns else _SPOT_BASIS


def _quote_time(row: dict[str, Any], basis: str, fetch_time: datetime) -> datetime | None:
    if basis != _TDX_BASIS:
        return fetch_time
    digits = re.sub(r"\D", "", str(row.get("date") or ""))[:8]
    if len(digits) != 8:
        return None
    try:
        return datetime.strptime(digits, "%Y%m%d").replace(hour=15, tzinfo=_BEIJING)
    except ValueError:
        return None


def _base_result(now: datetime, basis: str) -> dict[str, Any]:
    return {
        "ok": False,
        "source": f"spot_snapshot.fetch_spot_dataframe ({basis})",
        "data_basis": basis,
        "local_time": now.isoformat(timespec="seconds"),
        "coverage": 0,
        "valid_quote_count": 0,
        "duplicate_count": 0,
        "null_count": 0,
        "candidate_count": 0,
        "candidate_count_basis": "provisional_price_screen_pending_corporate_action_check",
        "industry_counts": {"unmapped": 0},
        "candidates": [],
    }


def _parse_quotes(df: pd.DataFrame, now: datetime, result: dict[str, Any], min_coverage: int) -> list[dict[str, Any]]:
    seen: set[str] = set()
    candidates: list[dict[str, Any]] = []
    active: list[tuple[float, datetime]] = []
    null_count = duplicate_count = mismatch_count = valid_quote_count = 0
    basis = str(result["data_basis"])
    for raw in df.to_dict("records"):
        code = normalize_spot_symbol(raw.get("代码"))
        if not _SYMBOL.fullmatch(code):
            null_count += 1
            continue
        symbol = f"{code}.{_suffix(code)}"
        if symbol in seen:
            duplicate_count += 1
            continue
        seen.add(symbol)
        price = _number(raw.get("最新价"))
        prev_close = _number(raw.get("昨收"))
        vendor_pct = _number(raw.get("涨跌幅"))
        if prev_close is None or prev_close <= 0:
            # spot_snapshot does not expose the tdx prev_close; recover it from pct_chg.
            prev_close = (
                price / (1.0 + vendor_pct / 100.0) if price and vendor_pct is not None and vendor_pct > -100 else None
            )
        amount = _number(raw.get("成交额"))
        traded_at = _quote_time(raw, basis, now)
        name = str(raw.get("名称") or raw.get("name") or "").upper()
        if price is None or price <= 0 or prev_close is None or prev_close <= 0 or traded_at is None or not name:
            null_count += 1
            continue
        valid_quote_count += 1
        if amount is not None and amount > 0:
            active.append((amount, traded_at))
        if "ST" in name or "退" in name:
            continue
        pct = (price / prev_close - 1) * 100
        if pct > -7:
            continue
        pct_mismatch = vendor_pct is not None and abs(vendor_pct - pct) > 0.5
        mismatch_count += int(pct_mismatch)
        age_seconds = round((now - traded_at).total_seconds())
        candidates.append(
            {
                "symbol": symbol,
                "price": price,
                "pct": round(pct, 3),
                "amount": amount,
                "timestamp": traded_at.isoformat(timespec="seconds"),
                "age_seconds": age_seconds,
                "needs_recheck": age_seconds > 60 or age_seconds < -60 or pct_mismatch,
            }
        )
    candidates.sort(key=lambda item: (item["pct"], item["symbol"]))
    result.update(
        coverage=len(seen),
        valid_quote_count=valid_quote_count,
        duplicate_count=duplicate_count,
        null_count=null_count,
        candidate_count=len(candidates),
        quote_pct_mismatch_count=mismatch_count,
        industry_counts={"unmapped": len(candidates)},
        candidates=[
            {key: candidate[key] for key in ("symbol", "price", "pct", "amount", "timestamp")}
            for candidate in candidates[:_PAGE_SIZE]
        ],
    )
    if valid_quote_count < min_coverage or duplicate_count or null_count > max(10, len(df) // 100):
        result["failure"] = "DATA_INCOMPLETE"
        return candidates
    if not active:
        result["failure"] = "NO_ACTIVE_QUOTES"
        return candidates
    newest = max((traded_at for _, traded_at in sorted(active, reverse=True)[:20]), default=None)
    result["active_latest_time"] = newest.isoformat(timespec="seconds") if newest else None
    if basis == _TDX_BASIS:
        # Post-close package: the previous session is the intended caliber, not staleness.
        result["market_state"] = "post_close_prior_session"
        result["ok"] = True
    elif newest is None or newest.date() != now.date():
        result["failure"] = "CORE_QUOTES_STALE"
    elif now.time() >= time(15) and newest.time() >= time(14, 57):
        result["market_state"] = "closed_next_day_observation_only"
        result["ok"] = True
    elif (now - newest).total_seconds() > 60 or (newest - now).total_seconds() > 60:
        result["failure"] = "CORE_QUOTES_STALE"
    else:
        result["market_state"] = "live"
        result["ok"] = True
    return candidates


def fetch_snapshot(
    *,
    now: datetime | None = None,
    spot_df: pd.DataFrame | None = None,
    min_coverage: int = _MIN_COVERAGE,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """Fetch one full-A spot snapshot without API keys or stale-cache fallback."""
    observed = (now or datetime.now(_BEIJING)).astimezone(_BEIJING)
    received = datetime.now(_BEIJING)
    if spot_df is None:
        try:
            spot_df = fetch_spot_dataframe()
        except Exception as exc:
            result = _base_result(observed, _SPOT_BASIS)
            result.update(
                failure="SPOT_FETCH_ERROR",
                exception_type=type(exc).__name__,
                received_time=received.isoformat(timespec="seconds"),
            )
            return result, []
    if not isinstance(spot_df, pd.DataFrame) or spot_df.empty or not {"代码", "最新价"}.issubset(spot_df.columns):
        result = _base_result(observed, _SPOT_BASIS)
        result["failure"] = "INVALID_PAYLOAD"
        return result, []
    basis = _detect_basis(spot_df)
    result = _base_result(observed, basis)
    result.update(
        row_count=len(spot_df),
        received_time=received.isoformat(timespec="seconds"),
    )
    return result, _parse_quotes(spot_df, observed if now is not None else received, result, min_coverage)


def _write_json(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), flush=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--interactive", action="store_true", help="Page through the in-memory candidate pool")
    args = parser.parse_args()
    result, candidates = fetch_snapshot()
    _write_json(result)
    if not result["ok"] or not args.interactive:
        return 0 if result["ok"] else 1
    for raw in sys.stdin:
        command = raw.strip().split()
        if command == ["quit"]:
            break
        if len(command) != 2 or command[0] != "page" or not command[1].isdigit():
            _write_json({"error": "USE_PAGE_NUMBER_OR_QUIT"})
            continue
        page = int(command[1])
        start = page * _PAGE_SIZE
        _write_json({"page": page, "candidates": candidates[start : start + _PAGE_SIZE]})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
