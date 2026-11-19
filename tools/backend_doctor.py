"""Diagnostics tool to check LLM configs, connection endpoints, and market data credentials."""

from __future__ import annotations

import importlib.util
import json
import logging
import os
import time
import urllib.request
from typing import Any

from integrations._llm_types import SUPPORTED_PROVIDERS
from integrations.llm_client import get_provider_credentials

logger = logging.getLogger(__name__)


def _ping_provider(provider: str, ping_url: str, model: str, base_url: str) -> dict[str, Any]:
    """Test connection to a provider's endpoint."""
    start_time = time.perf_counter()
    try:
        req = urllib.request.Request(ping_url, method="HEAD")
        with urllib.request.urlopen(req, timeout=5):
            pass
        latency = int((time.perf_counter() - start_time) * 1000)
        return {
            "status": "healthy",
            "api_key_configured": True,
            "model": model,
            "base_url": base_url,
            "latency_ms": latency,
            "error": None,
        }
    except Exception:
        try:
            start_time = time.perf_counter()
            req = urllib.request.Request(ping_url, method="GET")
            with urllib.request.urlopen(req, timeout=5):
                pass
            latency = int((time.perf_counter() - start_time) * 1000)
            return {
                "status": "healthy",
                "api_key_configured": True,
                "model": model,
                "base_url": base_url,
                "latency_ms": latency,
                "error": None,
            }
        except Exception as e2:
            logger.debug("Failed LLM connection check for %s: %s", provider, e2)
            return {
                "status": "connection_error",
                "api_key_configured": True,
                "model": model,
                "base_url": base_url,
                "latency_ms": None,
                "error": str(e2),
            }


def _diagnose_llm_providers() -> dict[str, dict[str, Any]]:
    """Check configuration and availability of LLM providers."""
    results = {}
    for provider in SUPPORTED_PROVIDERS:
        api_key, model, base_url = get_provider_credentials(provider)
        if not api_key:
            results[provider] = {
                "status": "unconfigured",
                "api_key_configured": False,
                "model": model,
                "base_url": base_url,
                "latency_ms": None,
                "error": None,
            }
            continue

        ping_url = base_url or "https://api.openai.com/v1"
        if provider == "gemini":
            ping_url = "https://generativelanguage.googleapis.com"
        results[provider] = _ping_provider(provider, ping_url, model, base_url)
    return results


def _check_tushare(token: str) -> dict[str, Any]:
    """Verify Tushare token and endpoint status."""
    tushare_url = "https://api.tushare.pro"
    start_time = time.perf_counter()
    try:
        req = urllib.request.Request(
            tushare_url,
            data=json.dumps(
                {
                    "api_name": "stock_basic",
                    "token": token,
                    "params": {"list_status": "L", "limit": 1},
                    "fields": "ts_code,name",
                }
            ).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=8) as response:
            res = json.loads(response.read().decode("utf-8"))
            if res.get("code") == 0:
                return {
                    "status": "healthy",
                    "token_configured": True,
                    "latency_ms": int((time.perf_counter() - start_time) * 1000),
                    "error": None,
                }
            return {
                "status": "invalid_credentials",
                "token_configured": True,
                "error": f"Tushare API error: {res.get('msg')}",
            }
    except Exception as e:
        return {
            "status": "connection_error",
            "token_configured": True,
            "error": str(e),
        }


def _diagnose_data_sources() -> dict[str, dict[str, Any]]:
    """Check configuration and health of data providers."""
    results = {}

    tushare_token = os.getenv("TUSHARE_TOKEN", "").strip()
    if not tushare_token:
        results["tushare"] = {
            "status": "unconfigured",
            "token_configured": False,
            "error": None,
        }
    else:
        results["tushare"] = _check_tushare(tushare_token)

    # 免费降级源无需密钥：检查模块是否可用、是否被环境变量关闭。
    fallback_sources = {
        "akshare": "DATA_SOURCE_DISABLE_AKSHARE",
        "baostock": "DATA_SOURCE_DISABLE_BAOSTOCK",
        "efinance": "DATA_SOURCE_DISABLE_EFINANCE",
        "tencent": "DATA_SOURCE_DISABLE_TENCENT",
        "sina": "DATA_SOURCE_DISABLE_SINA",
    }
    for source, disable_env in fallback_sources.items():
        if os.getenv(disable_env, "").strip():
            results[source] = {"status": "disabled", "error": None}
        elif importlib.util.find_spec(f"integrations.data_source_{source}") is None:
            results[source] = {"status": "unavailable", "error": "module not found"}
        else:
            results[source] = {"status": "healthy", "error": None}
    return results


def diagnose_backend() -> dict[str, Any]:
    """Diagnose generation backends and data source credentials, reporting latency and status."""
    llm_providers = _diagnose_llm_providers()
    data_sources = _diagnose_data_sources()

    any_llm_healthy = any(p.get("status") == "healthy" for p in llm_providers.values())
    return {
        "timestamp": time.time(),
        "ok": any_llm_healthy,
        "llm_providers": llm_providers,
        "data_sources": data_sources,
    }
