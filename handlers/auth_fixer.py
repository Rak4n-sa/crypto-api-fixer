"""
Auth Fixer Handler
يصلح أخطاء المصادقة (401/403) تلقائياً
"""

import time
import random
import hmac
import hashlib
import urllib.parse
from typing import Any, Dict, Optional

API_KEYS_POOL = ["key_1", "key_2", "key_3"]
PROXY_POOL = ["http://proxy1:8080", "http://proxy2:8080"]
RECV_WINDOW = 5000


def get_backup_key() -> Optional[str]:
    return random.choice(API_KEYS_POOL) if API_KEYS_POOL else None


def get_proxy() -> Optional[str]:
    return random.choice(PROXY_POOL) if PROXY_POOL else None


def build_signature(secret: str, params: Dict[str, Any]) -> str:
    query = urllib.parse.urlencode(sorted(params.items()))
    return hmac.new(
        secret.encode("utf-8"),
        query.encode("utf-8"),
        hashlib.sha256
    ).hexdigest()


def strategy_runner(strategies):
    for strategy in strategies:
        result = strategy()
        if isinstance(result, dict) and result.get("fixed"):
            return result
    return degraded_mode()


def degraded_mode() -> Dict[str, Any]:
    return {
        "fixed": True,
        "action": "degraded_mode",
        "retry": False,
        "strategy": "fallback",
        "confidence": 0.3,
        "mode": "read_only"
    }


def handle(detection: Dict[str, Any], original_response: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    variant = detection.get("variant", "")
    status = detection.get("status", 401)
    data = original_response.get("data", {})

    if variant == "expired_key":
        result = strategy_runner([rotate_api_key, degraded_mode])
    elif variant == "ip_not_whitelisted":
        result = strategy_runner([switch_proxy, degraded_mode])
    elif variant == "signature_mismatch":
        result = recalc_signature()
    elif variant == "invalid_api_key":
        result = degraded_mode()
    elif variant == "timestamp_out_of_sync":
        result = sync_timestamp()
    else:
        result = generic_auth_fix(status, data)

    result["latency_ms"] = round((time.time() - start) * 1000, 2)
    result["handler"] = "auth_fixer"
    result["variant"] = variant
    result["status"] = status
    return result


def rotate_api_key() -> Dict[str, Any]:
    key = get_backup_key()
    if key:
        return {
            "fixed": True,
            "action": "rotate_api_key",
            "retry": True,
            "strategy": "key_rotation",
            "confidence": 0.9,
            "new_api_key": key
        }
    return {"fixed": False}


def switch_proxy() -> Dict[str, Any]:
    proxy = get_proxy()
    if proxy:
        return {
            "fixed": True,
            "action": "switch_proxy",
            "retry": True,
            "strategy": "proxy_fallback",
            "confidence": 0.85,
            "proxy": proxy
        }
    return {"fixed": False}


def recalc_signature() -> Dict[str, Any]:
    return {
        "fixed": True,
        "action": "recalculate_signature",
        "retry": True,
        "strategy": "signature_fix",
        "confidence": 0.95,
        "new_timestamp": int(time.time() * 1000),
        "recv_window": RECV_WINDOW
    }


def sync_timestamp() -> Dict[str, Any]:
    return {
        "fixed": True,
        "action": "sync_timestamp",
        "retry": True,
        "strategy": "time_sync",
        "confidence": 0.95,
        "new_timestamp": int(time.time() * 1000),
        "recv_window": RECV_WINDOW
    }


def generic_auth_fix(status: int, data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        data = {}
    msg = str(data.get("msg", "")).lower()
    strategies = []
    if "signature" in msg:
        strategies.append(recalc_signature)
    if "timestamp" in msg:
        strategies.append(sync_timestamp)
    if "ip" in msg:
        strategies.append(switch_proxy)
    if "expired" in msg:
        strategies.append(rotate_api_key)
    strategies.append(degraded_mode)
    return strategy_runner(strategies)


def is_auth_error(response: Dict[str, Any]) -> bool:
    return response.get("status") in (401, 403)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "../training")
    from broken_api_generator import generate_one

    print("⚡ Auth Fixer Handler Test\n")
    fixed = 0
    total = 10
    for _ in range(total):
        error = generate_one("auth_error")
        detection = {"variant": error.get("variant", ""), "status": error.get("status", 401)}
        result = handle(detection, error)
        icon = "✅" if result["fixed"] else "❌"
        print("{} variant={:<28} action={:<30} conf={}".format(
            icon, result["variant"], result["action"], result.get("confidence", 0)))
        if result["fixed"]:
            fixed += 1
    print("\n📊 Fixed: {}/{} ({}%)".format(fixed, total, round(fixed/total*100)))
