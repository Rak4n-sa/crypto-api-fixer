"""
Detector
يحدد نوع المشكلة من الـ API response
"""

import time
from typing import Any, Dict, Optional

STALE_THRESHOLD_SECONDS = 5
PRICE_MISMATCH_THRESHOLD = 1.0
LATENCY_THRESHOLD_MS = 500


def detect(response: Dict[str, Any]) -> Dict[str, Any]:
    status = response.get("status", 200)
    data = response.get("data", {})
    headers = response.get("headers", {})
    error_type = response.get("error_type")

    if error_type:
        return _build_result(
            error_type=error_type,
            variant=response.get("variant", "unknown"),
            status=status,
            details=data,
        )

    if status in (429, 503):
        return _build_result(
            error_type="rate_limit",
            variant="429_with_retry" if headers.get("retry-after") else "429_no_retry",
            status=status,
            details={"retry_after": headers.get("retry-after")},
        )

    if status == 401:
        return _build_result("auth_error", "invalid_api_key", status, data)

    if status == 403:
        msg = str(data.get("msg", "")).lower()
        variant = (
            "signature_mismatch" if "signature" in msg else
            "ip_not_whitelisted" if "ip" in msg else
            "key_permission" if "permission" in msg else
            "forbidden"
        )
        return _build_result("auth_error", variant, status, data)

    if status in (502, 504) or status == 0:
        variant = (
            "gateway_timeout" if status == 504 else
            "bad_gateway" if status == 502 else
            "connection_refused"
        )
        return _build_result("endpoint_down", variant, status, data)

    if status == 500:
        return _build_result("unexpected_error", "internal_server", status, data)

    if status == 200:
        stale = _check_stale(data)
        if stale:
            return _build_result("stale_data", stale["variant"], status, stale)

    if status == 200 and isinstance(data, dict) and "prices" in data:
        mismatch = _check_price_mismatch(data)
        if mismatch:
            return _build_result("price_mismatch", "high_spread", status, mismatch)

    if status == 200:
        broken = _check_json(data)
        if broken:
            return _build_result("json_broken", broken["variant"], status, broken)

    if status == 200:
        risk = _check_financial_risk(data)
        if risk:
            return _build_result("financial_risk", risk["variant"], status, risk)

    if response.get("error_type") == "websocket_dead" or _check_websocket(data):
        return _build_result("websocket_dead", "silent_disconnect", 0, data)

    return _build_result("none", "ok", status, {})


def _check_stale(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    now = time.time()
    if not isinstance(data, dict):
        return None
    # إذا مافي timestamp أصلاً — مو stale
    if "timestamp" not in data:
        return None
    ts = data.get("timestamp")
    if ts is None:
        return None
    if not isinstance(ts, (int, float)):
        return {"variant": "wrong_format_timestamp", "timestamp": ts}
    age = now - ts
    if age > STALE_THRESHOLD_SECONDS:
        return {"variant": "old_timestamp", "age_seconds": round(age, 1)}
    return None


def _check_price_mismatch(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    prices = data.get("prices", {})
    if not isinstance(prices, dict) or len(prices) < 2:
        return None
    values = list(prices.values())
    if not all(isinstance(v, (int, float)) for v in values):
        return None
    min_p, max_p = min(values), max(values)
    if min_p == 0:
        return None
    spread_pct = ((max_p - min_p) / min_p) * 100
    if spread_pct > PRICE_MISMATCH_THRESHOLD:
        return {"variant": "high_spread", "spread_pct": round(spread_pct, 2), "prices": prices}
    return None


def _to_float(value: Any) -> Optional[float]:
    """يحوّل أي قيمة لـ float إذا ممكن — يقبل string أو number"""
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except (ValueError, TypeError):
            return None
    return None


def _check_json(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(data, dict):
        return {"variant": "invalid_format"}
    if not data:
        return {"variant": "empty_response"}

    # فحص price — نقبل string رقمي أو number (Binance يرسل string)
    price_raw = data.get("price")
    if price_raw is not None:
        price = _to_float(price_raw)
        if price is None:
            return {"variant": "wrong_types", "field": "price", "value": price_raw}

    # فحص null values — بس على الحقول المهمة فقط
    important_fields = ["price", "volume", "timestamp"]
    for field in important_fields:
        if field in data and data[field] is None:
            return {"variant": "null_values", "field": field}

    return None


def _check_financial_risk(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    if not isinstance(data, dict):
        return None
    latency = data.get("latency_ms")
    if isinstance(latency, (int, float)) and latency > LATENCY_THRESHOLD_MS:
        return {"variant": "latency_spike", "latency_ms": latency}
    change_pct = data.get("change_pct")
    if isinstance(change_pct, (int, float)) and change_pct > 3.0:
        return {"variant": "price_spike", "change_pct": change_pct}
    depth = data.get("order_book_depth")
    required = data.get("required_depth")
    if isinstance(depth, (int, float)) and isinstance(required, (int, float)) and depth < required:
        return {"variant": "low_liquidity", "depth": depth}
    return None


def _check_websocket(data: Dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    if data.get("connected") and data.get("last_message_ago_seconds", 0) > 30:
        return True
    if data.get("last_heartbeat_ago", 0) > 60:
        return True
    return False


SEVERITY_MAP = {
    "stale_data": "high", "rate_limit": "high", "endpoint_down": "high",
    "unexpected_error": "medium", "price_mismatch": "critical",
    "json_broken": "medium", "auth_error": "high", "financial_risk": "critical",
    "websocket_dead": "medium", "key_permission": "high", "none": "none",
}

FINANCIAL_RISK_TYPES = {"stale_data", "price_mismatch", "financial_risk"}


def _build_result(error_type: str, variant: str, status: int, details: Any) -> Dict[str, Any]:
    return {
        "error_type": error_type,
        "variant": variant,
        "status": status,
        "severity": SEVERITY_MAP.get(error_type, "medium"),
        "financial_risk": error_type in FINANCIAL_RISK_TYPES,
        "details": details,
    }


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "../training")
    from broken_api_generator import generate_one, ERROR_TYPES

    print("🔍 Detector Test\n")
    correct = 0
    for error_type in ERROR_TYPES:
        sample = generate_one(error_type)
        result = detect(sample)
        match = result["error_type"] == error_type
        correct += 1 if match else 0
        icon = "✅" if match else "❌"
        print("{} {:<25} → detected: {:<25} severity={}".format(
            icon, error_type, result["error_type"], result["severity"]))
    total = len(ERROR_TYPES)
    print("\n📊 Accuracy: {}/{} ({}%)".format(
        correct, total, round(correct / total * 100) if total > 0 else 0))
