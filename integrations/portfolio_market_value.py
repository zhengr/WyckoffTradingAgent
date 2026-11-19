"""Latest quote and official FX inputs for portfolio valuation."""

from __future__ import annotations

import os
from typing import Any

import requests

from core.portfolio_symbol import is_cn_portfolio_code, normalize_portfolio_code
from core.portfolio_valuation import portfolio_currency
from integrations.recommendation_tracking_common import resolve_quote_price

_ECB_RATES_URL = "https://api.frankfurter.dev/v2/rates"
_FX_TIMEOUT_SECONDS = 6


def load_portfolio_marks(
    positions: list[dict[str, Any]],
) -> tuple[dict[str, float], dict[str, float]]:
    prices, _prev_closes, rates = load_portfolio_quote_marks(positions)
    return prices, rates


def load_portfolio_quote_marks(
    positions: list[dict[str, Any]],
) -> tuple[dict[str, float], dict[str, float], dict[str, float]]:
    """最新价、昨收、人民币汇率。昨收只服务当日盈亏，不影响市值。"""
    codes = _position_codes(positions)
    if not codes:
        return {}, {}, {"CNY": 1.0}
    quotes = _fetch_quote_map(codes)
    prices = {code: _quote_price(code, quotes) for code in codes}
    prev_closes = {code: _quote_prev_close(code, quotes) for code in codes}
    currencies = {portfolio_currency(code) for code in codes}
    return prices, prev_closes, load_cny_rates(currencies)


def _fetch_quote_map(codes: list[str]) -> dict[str, dict[str, Any]]:
    """A 股走全市场 spot 快照，港美股走免 key 的腾讯日线 provider。"""
    from utils.safe import safe_float

    quotes: dict[str, dict[str, Any]] = {}
    cn_codes = [code for code in codes if is_cn_portfolio_code(code)]
    if cn_codes:
        from integrations import spot_snapshot

        spot_map = spot_snapshot.load_spot_snapshot_map()
        for code in cn_codes:
            row = spot_map.get(code)
            if not row:
                continue
            close = safe_float(row.get("close"), 0.0)
            raw_pct = row.get("pct_chg")
            pct = safe_float(raw_pct, 0.0)
            # spot_snapshot 未透出昨收：用涨跌幅反推，仅用于当日盈亏。
            # 涨跌幅缺失时留 0，让当日盈亏退回今开成本基准而不是伪造 0% 涨跌。
            prev_close = close / (1.0 + pct / 100.0) if raw_pct is not None and close > 0 and pct > -100 else 0.0
            quotes[code] = {
                "last_price": close,
                "close": close,
                "prev_close": prev_close,
                "pct_chg": pct,
            }
    hk_us_codes = [code for code in codes if not is_cn_portfolio_code(code)]
    if hk_us_codes:
        from integrations.data_source_hk_us import fetch_quote_map

        quotes.update(fetch_quote_map(hk_us_codes))
    return quotes


def load_cny_rates(currencies: set[str]) -> dict[str, float]:
    rates = {"CNY": 1.0}
    foreign = sorted(currency for currency in currencies if currency != "CNY")
    unresolved: list[str] = []
    for currency in foreign:
        override = _positive_env_float(f"PORTFOLIO_{currency}_CNY_RATE")
        if override is None:
            unresolved.append(currency)
        else:
            rates[currency] = override
    if unresolved:
        rates.update(_fetch_ecb_cny_rates(unresolved))
    return rates


def _position_codes(positions: list[dict[str, Any]]) -> list[str]:
    codes = {
        normalize_portfolio_code(str(row.get("code", "") or ""))
        for row in positions
        if int(row.get("shares", 0) or 0) > 0
    }
    return sorted(code for code in codes if code)


def _quote_row(code: str, quotes: dict[str, dict[str, Any]]) -> dict[str, Any]:
    if code in quotes:
        return quotes[code]
    bare = str(code or "").strip().upper()
    if "." in bare:
        bare = bare.split(".", 1)[0]
    for key in (f"{bare}.SH", f"{bare}.SZ", f"{bare}.BJ", bare):
        if key in quotes:
            return quotes[key]
    return {}


def _quote_price(code: str, quotes: dict[str, dict[str, Any]]) -> float:
    return resolve_quote_price(_quote_row(code, quotes))


def _quote_prev_close(code: str, quotes: dict[str, dict[str, Any]]) -> float:
    from utils.safe import safe_float

    row = _quote_row(code, quotes)
    for key in ("prev_close", "pre_close", "previous_close", "preclose"):
        value = safe_float(row.get(key), 0.0)
        if value > 0:
            return value
    return 0.0


def _positive_env_float(name: str) -> float | None:
    raw = os.getenv(name, "").strip()
    if not raw:
        return None
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


def _fetch_ecb_cny_rates(currencies: list[str]) -> dict[str, float]:
    response = requests.get(
        _ECB_RATES_URL,
        params={"base": "CNY", "quotes": ",".join(currencies), "providers": "ECB"},
        timeout=_FX_TIMEOUT_SECONDS,
    )
    response.raise_for_status()
    rows = response.json()
    rates: dict[str, float] = {}
    for row in rows if isinstance(rows, list) else []:
        currency = str(row.get("quote", "") or "").upper()
        cny_to_foreign = float(row.get("rate", 0.0) or 0.0)
        if currency in currencies and cny_to_foreign > 0:
            rates[currency] = 1.0 / cny_to_foreign
    return rates
