"""
Error Handler
يحل الأخطاء غير المتوقعة (500، null values، wrong types)
بدون Claude API — حل مباشر فوري
"""

import time
from typing import Any, Dict

MAX_RETRIES = 2
RETRY_DELAY = 1.0


def handle(detection: Dict[str, Any], original_response: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    variant = detection.get("variant", "")
    data = original_response.get("data", {})

    if not isinstance(data, dict):
        data = {}

    if variant == "internal_server":
        result = _handle_500(data)
    elif variant == "null_values":
        result = _handle_null_values(data)
    elif variant == "wrong_types":
        result = _handle_wrong_types(data)
    elif variant == "empty_response":
        result = _handle_empty(data)
    elif variant == "server_crash":
        result = _handle_crash(data)
    else:
        result = _handle_generic(data, detection.get("status", 500))

    result["latency_ms"] = round((time.time() - start) * 1000, 2)
    result["handler"] = "error_handler"
    result["variant"] = variant
    return result


def _handle_500(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "fixed": True,
        "action": "retry_after_500",
        "data": {},
        "retry": True,
        "wait_seconds": RETRY_DELAY,
        "alert": False,
        "log": True,
    }


def _handle_null_values(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {"fixed": False, "action": "rejected_invalid_data", "data": {}, "log": True}

    cleaned = {k: v for k, v in data.items() if v is not None}

    if not cleaned:
        return {"fixed": False, "action": "rejected_all_null", "data": {}, "log": True}

    return {
        "fixed": True,
        "action": "removed_null_values",
        "data": cleaned,
        "removed_fields": [k for k, v in data.items() if v is None],
        "log": True,
    }


def _handle_wrong_types(data: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {"fixed": False, "action": "rejected_invalid_data", "data": {}, "log": True}

    fixed_data = {}
    failed_fields = []

    for key, value in data.items():
        fixed = _try_fix_type(key, value)
        if fixed is not None:
            fixed_data[key] = fixed
        else:
            failed_fields.append(key)

    if not fixed_data:
        return {
            "fixed": False,
            "action": "rejected_wrong_types",
            "data": {},
            "failed_fields": failed_fields,
            "log": True,
        }

    return {
        "fixed": True,
        "action": "fixed_wrong_types",
        "data": fixed_data,
        "failed_fields": failed_fields,
        "log": True,
    }


def _handle_empty(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "fixed": True,
        "action": "retry_empty_response",
        "data": {},
        "retry": True,
        "wait_seconds": RETRY_DELAY,
        "log": True,
    }


def _handle_crash(data: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "fixed": True,
        "action": "alert_and_failover",
        "data": {},
        "retry": False,
        "use_backup": True,
        "alert": True,
        "log": True,
        "trace": data.get("trace", "") if isinstance(data, dict) else "",
    }


def _handle_generic(data: Dict[str, Any], status: int) -> Dict[str, Any]:
    return {
        "fixed": True,
        "action": "generic_retry",
        "data": data if isinstance(data, dict) else {},
        "retry": True,
        "wait_seconds": RETRY_DELAY,
        "log": True,
    }


def _try_fix_type(key: str, value: Any) -> Any:
    if key in ("price", "volume", "amount", "qty"):
        try:
            return float(str(value).replace(",", "").strip())
        except (ValueError, TypeError):
            return None
    if key == "timestamp":
        try:
            return float(value)
        except (ValueError, TypeError):
            return time.time()
    if key == "symbol":
        return str(value) if value else None
    return value


def is_unexpected_error(response: Dict[str, Any]) -> bool:
    status = response.get("status", 200)
    data = response.get("data", {})
    if status == 500:
        return True
    if isinstance(data, dict) and any(v is None for v in data.values()):
        return True
    return False


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "../training")
    from broken_api_generator import generate_one

    print("⚡ Error Handler Test\n")
    fixed = 0
    total = 10
    for i in range(total):
        error = generate_one("unexpected_error")
        detection = {"variant": error.get("variant", ""), "status": error.get("status", 500)}
        result = handle(detection, error)
        icon = "✅" if result["fixed"] else "❌"
        print("{} variant={:<22} action={:<30} latency={}ms".format(
            icon, result["variant"], result["action"], result["latency_ms"]))
        if result["fixed"]:
            fixed += 1
    print("\n📊 Fixed: {}/{} ({}%)".format(fixed, total, round(fixed/total*100)))
