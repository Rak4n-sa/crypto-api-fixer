"""
Fixer A
يقترح الحل الأول — rule-based منهج محافظ
fix-in-place: يصلح في نفس المكان
"""

from typing import Any, Dict, List

RULES: Dict[str, List[Dict[str, Any]]] = {
    "stale_data": [
        {"condition": "old_timestamp", "action": "refetch_from_primary", "confidence": 0.9},
        {"condition": "missing_timestamp", "action": "add_current_timestamp", "confidence": 0.8},
        {"condition": "wrong_format", "action": "fetch_from_backup", "confidence": 0.85},
    ],
    "rate_limit": [
        {"condition": "429_with_retry", "action": "wait_retry_after", "confidence": 0.95},
        {"condition": "429_no_retry", "action": "exponential_backoff", "confidence": 0.85},
        {"condition": "503", "action": "switch_to_backup", "confidence": 0.9},
    ],
    "json_broken": [
        {"condition": "malformed", "action": "extract_partial_json", "confidence": 0.7},
        {"condition": "schema_changed", "action": "remap_known_schema", "confidence": 0.8},
        {"condition": "missing_fields", "action": "fetch_missing_from_backup", "confidence": 0.75},
        {"condition": "nested", "action": "flatten_and_extract", "confidence": 0.85},
    ],
    "auth_error": [
        {"condition": "signature", "action": "recalculate_signature", "confidence": 0.95},
        {"condition": "timestamp", "action": "sync_timestamp", "confidence": 0.95},
        {"condition": "expired", "action": "rotate_api_key", "confidence": 0.85},
        {"condition": "ip", "action": "switch_proxy", "confidence": 0.8},
    ],
    "price_mismatch": [
        {"condition": "high_spread", "action": "use_median_price", "confidence": 0.9},
        {"condition": "outlier", "action": "exclude_outlier", "confidence": 0.95},
    ],
    "financial_risk": [
        {"condition": "price_spike", "action": "pause_and_alert", "confidence": 1.0},
        {"condition": "low_liquidity", "action": "reduce_position", "confidence": 0.9},
        {"condition": "latency", "action": "switch_to_limit_orders", "confidence": 0.85},
    ],
    "endpoint_down": [
        {"condition": "any", "action": "switch_to_backup_endpoint", "confidence": 0.95},
    ],
    "websocket_dead": [
        {"condition": "any", "action": "reconnect_websocket", "confidence": 0.9},
    ],
    "key_permission": [
        {"condition": "withdrawal", "action": "alert_critical_disable", "confidence": 1.0},
        {"condition": "any", "action": "switch_to_trading_key", "confidence": 0.85},
    ],
    "unexpected_error": [
        {"condition": "null", "action": "remove_null_values", "confidence": 0.85},
        {"condition": "wrong_type", "action": "fix_types", "confidence": 0.8},
        {"condition": "any", "action": "retry_once", "confidence": 0.75},
    ],
}


def propose(detection: Dict[str, Any], original_response: Dict[str, Any]) -> Dict[str, Any]:
    error_type = str(detection.get("error_type", "") or "")
    variant = str(detection.get("variant", "") or "")
    rules = RULES.get(error_type, [])

    if not rules:
        return {
            "agent": "fixer_a",
            "action": "no_rule_found",
            "confidence": 0.0,
            "approach": "conservative",
        }

    best = _find_best_rule(rules, variant)

    return {
        "agent": "fixer_a",
        "action": best["action"],
        "confidence": best["confidence"],
        "approach": "conservative",
        "error_type": error_type,
        "variant": variant,
        "reasoning": "rule-based: {} -> {}".format(best["condition"], best["action"]),
    }


def _find_best_rule(rules: List[Dict[str, Any]], variant: str) -> Dict[str, Any]:
    variant_lower = variant.lower()
    for rule in rules:
        condition = str(rule.get("condition", "")).lower()
        if condition == "any":
            continue
        if condition in variant_lower or variant_lower in condition:
            return rule
    any_rule = next((r for r in rules if r.get("condition") == "any"), None)
    if any_rule:
        return any_rule
    return max(rules, key=lambda r: r.get("confidence", 0))
