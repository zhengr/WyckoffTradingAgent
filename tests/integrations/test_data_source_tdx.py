"""通达信盘后包 provider 与 spot 快照回退测试（不发真实网络请求）。"""

from __future__ import annotations

import io
import struct
import zipfile

import pytest

import integrations.data_source_tdx as tdx_provider


def _make_cod(code: str, seq: int, name: str) -> bytes:
    rec = bytearray(150)
    rec[0:6] = code.encode("ascii")
    struct.pack_into("<H", rec, 32, seq)
    rec[40:40 + len(name.encode("gbk"))] = name.encode("gbk")
    return bytes(rec)


def _make_md1(prev: float, o: float, h: float, l: float, c: float, vol: int, amount: float) -> bytes:
    block = bytearray(512)
    struct.pack_into("<d", block, 4, prev)
    struct.pack_into("<4d", block, 12, o, h, l, c)
    struct.pack_into("<Q", block, 56, vol)
    struct.pack_into("<d", block, 72, amount)
    return bytes(block)


def _build_fake_package(ymd: str, sh_codes: list[tuple[str, str]]) -> bytes:
    """构造最小合法包：凑够 sh 下限行数（10000），用重复的空价行填充。"""
    cod = b"".join(_make_cod(code, i, name) for i, (code, name) in enumerate(sh_codes))
    md1 = b"".join(
        _make_md1(10.0, 10.0, 10.5, 9.8, 10.2 + (i % 10) * 0.01, 1000, 10200.0)
        for i in range(len(sh_codes))
    )
    # sz/bj 给下限以上的占位行
    sz_codes = [(f"{i:06d}", f"S{i}") for i in range(3000)]
    bj_codes = [(f"{i:06d}", f"B{i}") for i in range(50)]
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr(f"sh{ymd[2:]}.cod", cod)
        z.writestr(f"sh{ymd[2:]}.md1", md1)
        z.writestr(f"sz{ymd[2:]}.cod", b"".join(_make_cod(c, i, n) for i, (c, n) in enumerate(sz_codes)))
        z.writestr(f"sz{ymd[2:]}.md1", b"".join(_make_md1(10, 10, 10.5, 9.8, 10.2, 1000, 10200) for _ in sz_codes))
        z.writestr(f"bj{ymd[2:]}.cod", b"".join(_make_cod(c, i, n) for i, (c, n) in enumerate(bj_codes)))
        z.writestr(f"bj{ymd[2:]}.md1", b"".join(_make_md1(10, 10, 10.5, 9.8, 10.2, 1000, 10200) for _ in bj_codes))
    return buf.getvalue()


def test_tdx_package_parses_all_markets_with_amount(monkeypatch) -> None:
    ymd = "20261118"
    sh = [(f"{600000 + i}", f"股{i}") for i in range(10000)]
    package = _build_fake_package(ymd, sh)

    class FakeResp:
        status_code = 200
        content = package

        def raise_for_status(self):
            return None

    monkeypatch.setattr(tdx_provider.requests, "get", lambda *a, **k: FakeResp())
    rows = tdx_provider.fetch_tdx_daily_snapshot(ymd)

    assert len(rows) == 10000 + 3000 + 50
    maotai_like = [r for r in rows if r["code"] == "600519"][0]
    assert maotai_like["close"] == pytest.approx(10.2 + (519 % 10) * 0.01)
    assert maotai_like["volume"] == 1000
    assert maotai_like["amount"] == pytest.approx(10200.0)
    assert maotai_like["market"] == "sh"


def test_tdx_package_rejects_non_trading_404(monkeypatch) -> None:
    class FakeResp:
        status_code = 404
        content = b"<html>"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(tdx_provider.requests, "get", lambda *a, **k: FakeResp())
    with pytest.raises(ValueError, match="无通达信盘后包"):
        tdx_provider.fetch_tdx_daily_snapshot("20261114")


def test_recent_trade_day_skips_weekend() -> None:
    assert tdx_provider.recent_trade_day("2026-11-14").isoformat() == "2026-11-13"
    assert tdx_provider.recent_trade_day("2026-11-16").isoformat() == "2026-11-16"
