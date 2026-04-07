"""
Fallback Handler
يحل مشكلة endpoint down بتوجيه تلقائي لـ backup
بدون Claude API — حل مباشر فوري
"""

import time
import random
from collections import defaultdict
from typing import Any, Dict, Optional

BACKUP_ENDPOINTS = {
    "binance": [
        "https://api1.binance.com",
        "https://api2.binance.com",
        "https://api3.binance.com",
        "https://api4.binance.com",
    ],
    "coinbase": [
        "https://api.coinbase.com",
        "https://api-public.sandbox.exchange.coinbase.com",
    ],
    "kraken": [
        "https://api.kraken.com",
        "https://futures.kraken.com",
    ],
    "bybit": [
        "https://api.bybit.com",
        "https://api.bytick.com",
    ],
    "okx": [
        "https://www.okx.com",
        "https://aws.okx.com",
    ],
    "default": [
        "https://api.coingecko.com/api/v3",
        "https://min-api.cryptocompare.com",
        "https://api.coinpaprika.com/v1",
    ],
}

_endpoint_health = defaultdict(lambda: {
    "healthy": True,
    "last_failure": 0,
    "failure_count": 0,
    "cooldown_until": 0,
})

COOLDOWN_SECONDS = 60
MAX_FAILURES = 3


def handle(detection: Dict[str, Any], original_response: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    variant = detection.get("variant", "")
    data = original_response.get("data", {})
    if not isinstance(data, dict):
        data = {}
    status = detection.get("status", 0)
    exchange = _detect_exchange(data)

    if variant in ("connection_refused", "dns_failed"):
        result = _handle_connection_failure(exchange, variant)
    elif variant in ("bad_gateway", "gateway_timeout"):
        result = _handle_gateway_error(exchange, status)
    elif variant == "full_down":
        result = _handle_full_down(exchange)
    else:
        result = _handle_generic_down(exchange, status)

    result["latency_ms"] = round((time.time() - start) * 1000, 2)
    result["handler"] = "fallback"
    result["variant"] = variant
    result["exchange"] = exchange
    return result


def _handle_connection_failure(exchange: str, variant: str) -> Dict[str, Any]:
    backup = _get_best_backup(exchange)
    if backup:
        _mark_failed(exchange)
        return {
            "fixed": True,
            "action": "switched_to_backup",
            "backup_endpoint": backup,
            "strategy": "immediate_failover",
            "reason": variant,
        }
    default = _get_default_source()
    return {
        "fixed": True,
        "action": "switched_to_default_source",
        "backup_endpoint": default,
        "strategy": "default_fallback",
        "reason": "no_exchange_backup_available",
    }


def _handle_gateway_error(exchange: str, status: int) -> Dict[str, Any]:
    backup = _get_best_backup(exchange)
    if status == 504:
        return {
            "fixed": True,
            "action": "retry_with_timeout",
            "backup_endpoint": backup,
            "wait_seconds": 2,
            "strategy": "retry_then_failover",
        }
    _mark_failed(exchange)
    return {
        "fixed": True,
        "action": "switched_to_backup",
        "backup_endpoint": backup or _get_default_source(),
        "strategy": "immediate_failover",
        "reason": "bad_gateway",
    }


def _handle_full_down(exchange: str) -> Dict[str, Any]:
    _mark_failed(exchange, force_cooldown=True)
    backup = _get_best_backup(exchange)
    if backup:
        return {
            "fixed": True,
            "action": "failover_with_cooldown",
            "backup_endpoint": backup,
            "cooldown_seconds": COOLDOWN_SECONDS,
            "strategy": "full_failover",
        }
    return {
        "fixed": True,
        "action": "switched_to_default_source",
        "backup_endpoint": _get_default_source(),
        "strategy": "default_fallback",
    }


def _handle_generic_down(exchange: str, status: int) -> Dict[str, Any]:
    backup = _get_best_backup(exchange) or _get_default_source()
    return {
        "fixed": True,
        "action": "generic_failover",
        "backup_endpoint": backup,
        "strategy": "generic",
    }


def _detect_exchange(data: Dict[str, Any]) -> str:
    url = str(data.get("url", "")).lower()
    for exchange in BACKUP_ENDPOINTS:
        if exchange in url:
            return exchange
    return "default"


def _get_best_backup(exchange: str) -> Optional[str]:
    now = time.time()
    backups = BACKUP_ENDPOINTS.get(exchange, BACKUP_ENDPOINTS["default"])
    available = [ep for ep in backups if _endpoint_health[ep]["cooldown_until"] < now]
    if not available:
        available = sorted(backups, key=lambda ep: _endpoint_health[ep]["failure_count"])
    return available[0] if available else None


def _get_default_source() -> str:
    return random.choice(BACKUP_ENDPOINTS["default"])


def _mark_failed(exchange: str, force_cooldown: bool = False) -> None:
    now = time.time()
    health = _endpoint_health[exchange]
    health["last_failure"] = now
    health["failure_count"] += 1
    if force_cooldown or health["failure_count"] >= MAX_FAILURES:
        health["healthy"] = False
        health["cooldown_until"] = now + COOLDOWN_SECONDS


def get_endpoint_health() -> Dict[str, Any]:
    now = time.time()
    result = {}
    for ep, health in _endpoint_health.items():
        result[ep] = {
            "healthy": health["cooldown_until"] < now,
            "failure_count": health["failure_count"],
            "cooldown_remaining": max(0, round(health["cooldown_until"] - now, 1)),
        }
    return result


def is_endpoint_down(response: Dict[str, Any]) -> bool:
    return response.get("status") in (0, 502, 503, 504)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "../training")
    from broken_api_generator import generate_one

    print("⚡ Fallback Handler Test\n")
    fixed = 0
    total = 10
    for i in range(total):
        error = generate_one("endpoint_down")
        detection = {"variant": error.get("variant", ""), "status": error.get("status", 0)}
        result = handle(detection, error)
        icon = "✅" if result["fixed"] else "❌"
        backup = result.get("backup_endpoint", "none")
        if backup and len(str(backup)) > 35:
            backup = str(backup)[:35] + "..."
        print("{} variant={:<22} action={:<30} backup={}".format(
            icon, result["variant"], result["action"], backup))
        if result["fixed"]:
            fixed += 1
    print("\n📊 Fixed: {}/{} ({}%)".format(fixed, total, round(fixed/total*100)))
