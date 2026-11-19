"""Tongdaxin (通达信) official daily post-market package provider.

通达信官网每日发布的全市场增量包（g4day/{YYYYMMDD}.zip，约 2.7MB），一次拿到
沪深北全部证券当日的开高低收/成交量(股)/成交额(元)。走 HTTP，海外网络可达，
且成交额是腾讯/新浪 K 线接口都没有的字段 —— 正好补上 spot 快照在海外拿不到
成交额（东财 spot 接口被封）的缺口。

与 ``fetch_stock_hist`` 的按股票历史链不同，本模块提供的是**单交易日全市场快照**，
因此接入点是 spot 快照回退，而不是历史 K 线链。解析器为纯标准库实现，无新增依赖。

布局参考 jing2uo/tdx2db（MIT），已与腾讯/新浪收盘价对账一致。
"""

from __future__ import annotations

import io
import logging
import math
import os
import re
import struct
import zipfile
import zlib
from datetime import date, datetime, timedelta

import requests

logger = logging.getLogger(__name__)

TDX_PACKAGE_URL = "https://www.tdx.com.cn/products/data/data/g4day/{ymd}.zip"
TDX_BJ_FIRST_DAY = "20220506"
TDX_MIN_PRICED = {"sh": 10000, "sz": 3000, "bj": 50}
_TIMEOUT_SECONDS = float(os.getenv("TDX_PACKAGE_TIMEOUT_SECONDS", "60"))
_HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}


def fetch_tdx_daily_snapshot(trade_day: str | date) -> list[dict]:
    """拉取某交易日全市场日线快照。

    返回每行含 date/market/code/name/prev_close/open/high/low/close/volume(股)/amount(元)。
    非交易日或当日包未发布时官网返回 404，抛 ValueError；包损坏抛 RuntimeError。
    """
    ymd = _normalize_ymd(trade_day)
    url = TDX_PACKAGE_URL.format(ymd=ymd)
    resp = requests.get(url, headers=_HEADERS, timeout=_TIMEOUT_SECONDS)
    if resp.status_code == 404:
        raise ValueError(f"{ymd} 无通达信盘后包：非交易日 / 当日未发布 / 早于官网保留范围")
    resp.raise_for_status()
    if not resp.content.startswith(b"PK"):
        raise RuntimeError("通达信盘后包不是 zip（可能是错误页）")
    try:
        return _parse_package(resp.content, ymd)
    except (zipfile.BadZipFile, zlib.error, EOFError) as exc:
        raise RuntimeError(f"通达信盘后包 {url} 解压失败: {type(exc).__name__}: {exc}") from exc


def _normalize_ymd(value: str | date) -> str:
    if isinstance(value, date):
        return value.strftime("%Y%m%d")
    text = re.sub(r"\D", "", str(value))
    if len(text) != 8:
        raise ValueError(f"通达信盘后包日期格式无效: {value}")
    return text


def _parse_package(content: bytes, ymd: str) -> list[dict]:
    archive = zipfile.ZipFile(io.BytesIO(content))
    names = set(archive.namelist())
    rows: list[dict] = []
    for market in ("sh", "sz", "bj"):
        cod_name, md1_name = f"{market}{ymd[2:]}.cod", f"{market}{ymd[2:]}.md1"
        if market == "bj" and ymd < TDX_BJ_FIRST_DAY and cod_name not in names and md1_name not in names:
            continue
        if cod_name not in names or md1_name not in names:
            raise RuntimeError(f"通达信盘后包缺少 {cod_name}/{md1_name}，格式可能已变")
        cod, md1 = archive.read(cod_name), archive.read(md1_name)
        if len(cod) % 150 or len(md1) % 512:
            raise RuntimeError(f"{market} 代码表/行情块长度不是整块，文件被截断")
        if len(cod) // 150 != len(md1) // 512:
            raise RuntimeError(f"{market} 代码表与行情块条数对不上")
        before, codes, seqs = len(rows), set(), set()
        for offset in range(0, len(cod), 150):
            record = cod[offset : offset + 150]
            code = record[0:6].rstrip(b"\x00 ").decode("ascii", "replace")
            seq = struct.unpack("<H", record[32:34])[0]
            if not re.fullmatch(r"[0-9]{6}", code):
                raise RuntimeError(f"通达信盘后包 {market} 出现非 6 位代码 {code!r}")
            if code in codes or seq in seqs:
                raise RuntimeError(f"通达信盘后包 {market} 代码/序号重复 ({code!r}, {seq})")
            codes.add(code)
            seqs.add(seq)
            block = md1[seq * 512 : (seq + 1) * 512]
            if len(block) != 512:
                raise RuntimeError(f"{market}{code} 行情块越界")
            prev_close = struct.unpack("<d", block[4:12])[0]
            open_, high, low, close = struct.unpack("<4d", block[12:44])
            amount = struct.unpack("<d", block[72:80])[0]
            if not all(math.isfinite(v) for v in (prev_close, open_, high, low, close, amount)):
                raise RuntimeError(f"{market}{code} 行情块出现非有限值，文件损坏")
            if close <= 0:
                continue
            volume = struct.unpack("<Q", block[56:64])[0]
            raw_name = record[40:72].split(b"\x00")[0]
            try:
                name = raw_name.decode("gbk").strip()
            except UnicodeDecodeError as exc:
                raise RuntimeError(f"{market}{code} 名称非 GBK，文件损坏") from exc
            if not name:
                raise RuntimeError(f"{market}{code} 有价格却无名称")
            rows.append(
                {
                    "date": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                    "market": market,
                    "code": code,
                    "name": name,
                    "prev_close": round(prev_close, 4),
                    "open": round(open_, 4),
                    "high": round(high, 4),
                    "low": round(low, 4),
                    "close": round(close, 4),
                    "volume": volume,
                    "amount": round(amount, 2),
                }
            )
        if len(rows) - before < TDX_MIN_PRICED[market]:
            raise RuntimeError(
                f"通达信盘后包 {market} 只有 {len(rows) - before} 条有价记录"
                f"（下限 {TDX_MIN_PRICED[market]}），文件残缺或格式已变"
            )
    return rows


def recent_trade_day(reference: str | date | None = None) -> date:
    """给 spot 快照用的最近交易日猜测：从参考日往前找最近的周一到周五。

    盘后包通常收盘后数小时发布；若当日包未发布，调用方捕获 ValueError 后再往前一天。
    """
    ref = reference or date.today()
    if isinstance(ref, str):
        ref = datetime.strptime(ref.replace("-", ""), "%Y%m%d").date()
    d = ref
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d
