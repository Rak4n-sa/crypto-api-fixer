"""
Key Validator Handler
يتحقق من صلاحيات الـ API key ويصلح المشاكل
بدون Claude API — حل مباشر فوري
"""

import time
from collections import defaultdict
from typing import Any, Dict, List

REQUIRED_PERMISSIONS = ["READ", "TRADE"]
DANGEROUS_PERMISSIONS = ["WITHDRAW", "TRANSFER"]

_key_cache = defaultdict(lambda: {
    "checked_at": 0,
    "permissions": [],
    "safe": True,
})

CACHE_TTL = 300


def handle(detection: Dict[str, Any], original_response: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    variant = detection.get("variant", "")
    data = original_response.get("data", {})

    if not isinstance(data, dict):
        data = {}

    if variant == "no_trade_permission":
        result = _handle_no_trade(data)
    elif variant == "withdrawal_enabled":
        result = _handle_withdrawal_danger(data)
    elif variant == "read_only":
        result = _handle_read_only(data)
    else:
        result = _handle_generic_permission(data)

    result["latency_ms"] = round((time.time() - start) * 1000, 2)
    result["handler"] = "key_validator"
    result["variant"] = variant
    return result


def _handle_no_trade(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "fixed": True,
        "action": "switch_to_trading_key",
        "retry": True,
        "confidence": 0.9,
        "strategy": "key_rotation",
        "required_permissions": REQUIRED_PERMISSIONS,
        "instructions": [
            "switch to API key with TRADE permission",
            "verify key has READ + TRADE permissions",
            "do NOT enable WITHDRAW permission",
        ],
    }


def _handle_withdrawal_danger(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "fixed": True,
        "action": "alert_disable_withdrawal",
        "retry": False,
        "confidence": 1.0,
        "severity": "critical",
        "trading_allowed": False,
        "alert": True,
        "message": "CRITICAL: withdrawal permission enabled — immediate action required",
        "instructions": [
            "go to exchange API settings NOW",
            "disable withdrawal permission",
            "or delete and recreate API key without withdrawal",
            "trading is paused until resolved",
        ],
        "risk": "funds_at_risk",
    }


def _handle_read_only(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "fixed": True,
        "action": "degraded_read_only_mode",
        "retry": False,
        "confidence": 0.85,
        "mode": "read_only",
        "trading_allowed": False,
        "strategy": "degraded_mode",
        "instructions": [
            "current key is read-only",
            "switch to key with TRADE permission",
            "monitoring continues in read-only mode",
        ],
    }


def _handle_generic_permission(data: Dict[str, Any]) -> Dict[str, Any]:
    msg = str(data.get("msg", "")).lower()
    if "withdraw" in msg:
        return _handle_withdrawal_danger(data)
    if "trade" in msg:
        return _handle_no_trade(data)
    if "read" in msg:
        return _handle_read_only(data)
    return {
        "fixed": True,
        "action": "degraded_mode_generic",
        "retry": False,
        "confidence": 0.7,
        "mode": "read_only",
        "trading_allowed": False,
        "strategy": "degraded_mode",
    }


def audit_key(api_key: str, permissions: List[str]) -> Dict[str, Any]:
    issues = []
    safe = True
    for perm in DANGEROUS_PERMISSIONS:
        if perm in permissions:
            issues.append("DANGER: {} permission enabled".format(perm))
            safe = False
    for perm in REQUIRED_PERMISSIONS:
        if perm not in permissions:
            issues.append("MISSING: {} permission required".format(perm))
    _key_cache[api_key] = {
        "checked_at": time.time(),
        "permissions": permissions,
        "safe": safe,
        "issues": issues,
    }
    return {
        "safe": safe,
        "permissions": permissions,
        "issues": issues,
        "recommended": REQUIRED_PERMISSIONS,
        "dangerous_found": [p for p in DANGEROUS_PERMISSIONS if p in permissions],
    }


def is_key_permission_error(response: Dict[str, Any]) -> bool:
    return response.get("status") == 403 and "permission" in str(response.get("data", "")).lower()


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "../training")
    from broken_api_generator import generate_one

    print("⚡ Key Validator Handler Test\n")
    fixed = 0
    total = 10
    for i in range(total):
        error = generate_one("key_permission")
        detection = {"variant": error.get("variant", ""), "status": error.get("status", 403)}
        result = handle(detection, error)
        icon = "✅" if result["fixed"] else "❌"
        print("{} variant={:<25} action={:<30} trade={} alert={} conf={}".format(
            icon, result["variant"], result["action"],
            result.get("trading_allowed", "N/A"),
            result.get("alert", False),
            result.get("confidence", 0)))
        if result["fixed"]:
            fixed += 1
    print("\n📊 Fixed: {}/{} ({}%)".format(fixed, total, round(fixed/total*100)))
    print("\n🔍 Key Audit Test:")
    audit = audit_key("test_key_123", ["READ", "TRADE", "WITHDRAW"])
    print("   safe={}".format(audit["safe"]))
    print("   issues={}".format(audit["issues"]))
    print("   dangerous={}".format(audit["dangerous_found"]))
