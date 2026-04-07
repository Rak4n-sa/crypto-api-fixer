"""
Risk Guard Handler
يحمي البوت من الخسائر المالية المباشرة
بدون Claude API — حل مباشر فوري
"""

import time
from typing import Any, Dict

PRICE_SPIKE_THRESHOLD = 3.0
LATENCY_THRESHOLD_MS = 500
MIN_ORDER_BOOK_DEPTH = 10
CIRCUIT_BREAKER_WINDOW = 60

_circuit_breaker = {
    "triggered": False,
    "triggered_at": 0,
    "reason": "",
}


def handle(detection: Dict[str, Any], original_response: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    variant = detection.get("variant", "")
    data = original_response.get("data", {})

    if not isinstance(data, dict):
        data = {}

    if _is_circuit_broken():
        result = _handle_circuit_broken()
    elif variant == "price_spike":
        result = _handle_price_spike(data)
    elif variant == "low_liquidity":
        result = _handle_low_liquidity(data)
    elif variant == "latency_spike":
        result = _handle_latency_spike(data)
    else:
        result = _handle_generic_risk(data)

    result["latency_ms"] = round((time.time() - start) * 1000, 2)
    result["handler"] = "risk_guard"
    result["variant"] = variant
    return result


def _handle_price_spike(data: Dict[str, Any]) -> Dict[str, Any]:
    change_pct = data.get("change_pct", 0)
    if not isinstance(change_pct, (int, float)):
        change_pct = 0

    if change_pct > 10:
        _trigger_circuit_breaker("price_spike_critical")
        return {
            "fixed": True,
            "action": "circuit_breaker_triggered",
            "trading_allowed": False,
            "reason": "extreme price spike {}%".format(change_pct),
            "confidence": 1.0,
            "alert": True,
            "resume_after_seconds": CIRCUIT_BREAKER_WINDOW,
        }

    return {
        "fixed": True,
        "action": "pause_trading_price_spike",
        "trading_allowed": False,
        "change_pct": change_pct,
        "confidence": 0.95,
        "alert": True,
        "resume_after_seconds": 30,
    }


def _handle_low_liquidity(data: Dict[str, Any]) -> Dict[str, Any]:
    depth = data.get("order_book_depth", 0)
    required = data.get("required_depth", MIN_ORDER_BOOK_DEPTH)

    if not isinstance(depth, (int, float)):
        depth = 0
    if not isinstance(required, (int, float)) or required == 0:
        required = MIN_ORDER_BOOK_DEPTH

    if depth < required * 0.3:
        return {
            "fixed": True,
            "action": "pause_trading_no_liquidity",
            "trading_allowed": False,
            "depth": depth,
            "required": required,
            "confidence": 1.0,
            "alert": True,
        }

    ratio = depth / required
    return {
        "fixed": True,
        "action": "reduce_position_size",
        "trading_allowed": True,
        "max_position_pct": round(ratio * 50, 1),
        "confidence": 0.8,
        "warning": "low liquidity — reduce size to {}%".format(round(ratio * 50, 1)),
    }


def _handle_latency_spike(data: Dict[str, Any]) -> Dict[str, Any]:
    latency = data.get("latency_ms", 0)
    if not isinstance(latency, (int, float)):
        latency = 0

    if latency > 2000:
        _trigger_circuit_breaker("latency_critical")
        return {
            "fixed": True,
            "action": "circuit_breaker_high_latency",
            "trading_allowed": False,
            "latency_ms": latency,
            "confidence": 1.0,
            "alert": True,
        }

    return {
        "fixed": True,
        "action": "switch_to_limit_orders",
        "trading_allowed": True,
        "order_type": "limit_only",
        "latency_ms": latency,
        "confidence": 0.85,
        "warning": "high latency — use limit orders only",
    }


def _handle_circuit_broken() -> Dict[str, Any]:
    remaining = max(0, round(
        CIRCUIT_BREAKER_WINDOW - (time.time() - _circuit_breaker["triggered_at"]), 1))
    return {
        "fixed": True,
        "action": "circuit_breaker_active",
        "trading_allowed": False,
        "reason": _circuit_breaker["reason"],
        "resume_in_seconds": remaining,
        "confidence": 1.0,
    }


def _handle_generic_risk(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "fixed": True,
        "action": "generic_risk_pause",
        "trading_allowed": False,
        "confidence": 0.7,
        "alert": True,
    }


def _trigger_circuit_breaker(reason: str) -> None:
    _circuit_breaker["triggered"] = True
    _circuit_breaker["triggered_at"] = time.time()
    _circuit_breaker["reason"] = reason


def _is_circuit_broken() -> bool:
    if not _circuit_breaker["triggered"]:
        return False
    elapsed = time.time() - _circuit_breaker["triggered_at"]
    if elapsed > CIRCUIT_BREAKER_WINDOW:
        _circuit_breaker["triggered"] = False
        return False
    return True


def reset_circuit_breaker() -> None:
    _circuit_breaker["triggered"] = False
    _circuit_breaker["triggered_at"] = 0
    _circuit_breaker["reason"] = ""


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "../training")
    from broken_api_generator import generate_one

    print("⚡ Risk Guard Handler Test\n")
    fixed = 0
    total = 10
    reset_circuit_breaker()
    for i in range(total):
        error = generate_one("financial_risk")
        detection = {"variant": error.get("variant", ""), "status": error.get("status", 200)}
        result = handle(detection, error)
        icon = "✅" if result["fixed"] else "❌"
        print("{} variant={:<18} action={:<35} trade={} conf={}".format(
            icon, result["variant"], result["action"],
            result.get("trading_allowed", False), result.get("confidence", 0)))
        if result["fixed"]:
            fixed += 1
    print("\n📊 Fixed: {}/{} ({}%)".format(fixed, total, round(fixed/total*100)))
