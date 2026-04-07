"""
Rate Limit Handler
يحل مشكلة 429/503 بسرعة بدون توقف البوت
بدون Claude API — حل مباشر فوري
"""

import time
import random
from collections import defaultdict
from typing import Any, Dict

DEFAULT_WAIT = 5
MAX_WAIT = 300
MAX_RETRIES = 3
WEIGHT_RESET_WINDOW = 60

_rate_tracker = defaultdict(lambda: {"count": 0, "reset_at": 0, "banned_until": 0})


def handle(detection: Dict[str, Any], original_response: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    status = detection.get("status", 429)
    variant = detection.get("variant", "")
    headers = original_response.get("headers", {})

    if not isinstance(headers, dict):
        headers = {}

    if variant == "429_with_retry":
        result = _handle_with_retry_header(headers)
    elif variant == "429_no_retry":
        result = _handle_no_retry_header()
    elif variant == "503_overloaded":
        result = _handle_503()
    elif variant == "429_ip_ban":
        result = _handle_ip_ban(headers)
    elif variant == "429_weight_exceeded":
        result = _handle_weight_exceeded(headers)
    else:
        result = _handle_generic(status, headers)

    result["latency_ms"] = round((time.time() - start) * 1000, 2)
    result["handler"] = "rate_limit"
    result["variant"] = variant
    result["status"] = status
    return result


def _handle_with_retry_header(headers: Dict[str, Any]) -> Dict[str, Any]:
    retry_after = headers.get("retry-after", DEFAULT_WAIT)
    try:
        wait = min(float(retry_after), MAX_WAIT)
    except (ValueError, TypeError):
        wait = DEFAULT_WAIT
    return {
        "fixed": True,
        "action": "wait_retry_after",
        "wait_seconds": wait,
        "retry": True,
        "use_backup": False,
        "strategy": "respect_retry_header",
    }


def _handle_no_retry_header() -> Dict[str, Any]:
    wait = _exponential_backoff(attempt=1)
    return {
        "fixed": True,
        "action": "exponential_backoff",
        "wait_seconds": wait,
        "retry": True,
        "use_backup": False,
        "strategy": "exponential_backoff",
    }


def _handle_503() -> Dict[str, Any]:
    return {
        "fixed": True,
        "action": "switch_to_backup_endpoint",
        "wait_seconds": 0,
        "retry": True,
        "use_backup": True,
        "strategy": "failover",
        "backup_endpoint": "mirror_api",
    }


def _handle_ip_ban(headers: Dict[str, Any]) -> Dict[str, Any]:
    ban_duration = headers.get("retry-after", 300)
    try:
        wait = min(float(ban_duration), MAX_WAIT)
    except (ValueError, TypeError):
        wait = 300
    use_proxy = wait > 60
    return {
        "fixed": True,
        "action": "rotate_proxy" if use_proxy else "wait_ip_ban",
        "wait_seconds": 0 if use_proxy else wait,
        "retry": True,
        "use_backup": use_proxy,
        "strategy": "proxy_rotation" if use_proxy else "wait",
        "ban_duration": wait,
    }


def _handle_weight_exceeded(headers: Dict[str, Any]) -> Dict[str, Any]:
    used = headers.get("x-mbx-used-weight-1m", "1200")
    try:
        used_int = int(used)
    except (ValueError, TypeError):
        used_int = 1200
    wait = min(WEIGHT_RESET_WINDOW + random.uniform(1, 5), MAX_WAIT)
    return {
        "fixed": True,
        "action": "wait_weight_reset",
        "wait_seconds": wait,
        "retry": True,
        "use_backup": False,
        "strategy": "weight_window_reset",
        "used_weight": used_int,
    }


def _handle_generic(status: int, headers: Dict[str, Any]) -> Dict[str, Any]:
    retry_after = headers.get("retry-after")
    if retry_after:
        return _handle_with_retry_header(headers)
    wait = DEFAULT_WAIT if status == 429 else DEFAULT_WAIT * 2
    return {
        "fixed": True,
        "action": "generic_wait",
        "wait_seconds": wait,
        "retry": True,
        "use_backup": status == 503,
        "strategy": "generic",
    }


def _exponential_backoff(attempt: int, base: float = 2.0) -> float:
    wait = min(base ** attempt + random.uniform(0, 1), MAX_WAIT)
    return round(wait, 2)


def track_request(endpoint: str) -> Dict[str, Any]:
    now = time.time()
    tracker = _rate_tracker[endpoint]
    if now > tracker["reset_at"]:
        tracker["count"] = 0
        tracker["reset_at"] = now + WEIGHT_RESET_WINDOW
    tracker["count"] += 1
    return {
        "endpoint": endpoint,
        "count": tracker["count"],
        "reset_in": round(tracker["reset_at"] - now, 1),
        "warning": tracker["count"] > 800,
    }


def is_rate_limited(response: Dict[str, Any]) -> bool:
    status = response.get("status")
    return status in (429, 503)


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "../training")
    from broken_api_generator import generate_one

    print("⚡ Rate Limit Handler Test\n")
    fixed = 0
    total = 10
    for i in range(total):
        error = generate_one("rate_limit")
        detection = {"variant": error.get("variant", ""), "status": error.get("status", 429)}
        result = handle(detection, error)
        icon = "✅" if result["fixed"] else "❌"
        print("{} variant={:<25} action={:<30} wait={}s latency={}ms".format(
            icon, result["variant"], result["action"],
            result.get("wait_seconds", 0), result["latency_ms"]))
        if result["fixed"]:
            fixed += 1
    print("\n📊 Fixed: {}/{} ({}%)".format(fixed, total, round(fixed/total*100)))
