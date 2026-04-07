"""
Fixer B
يقترح الحل الثاني — strategy-based (هروب وليس إصلاح)
A = يصلح في نفس المكان
B = يهرب من المشكلة لمكان آخر
"""

from typing import Any, Dict

STRATEGIES: Dict[str, str] = {
    "stale_data":       "switch_to_backup_source_immediately",
    "rate_limit":       "switch_to_backup_endpoint",
    "endpoint_down":    "try_all_backups_parallel",
    "unexpected_error": "switch_to_backup_endpoint",
    "price_mismatch":   "fetch_from_third_exchange",
    "json_broken":      "fetch_complete_response_fresh",
    "auth_error":       "use_secondary_key_immediately",
    "financial_risk":   "immediate_circuit_break",
    "websocket_dead":   "fallback_to_rest_polling",
    "key_permission":   "use_read_only_degraded_mode",
}

CONFIDENCE: Dict[str, float] = {
    "stale_data":       0.88,
    "rate_limit":       0.90,
    "endpoint_down":    0.92,
    "unexpected_error": 0.80,
    "price_mismatch":   0.87,
    "json_broken":      0.78,
    "auth_error":       0.88,
    "financial_risk":   0.98,
    "websocket_dead":   0.88,
    "key_permission":   0.82,
}


def propose(detection: Dict[str, Any], original_response: Dict[str, Any]) -> Dict[str, Any]:
    error_type = str(detection.get("error_type", "") or "").lower()
    variant = str(detection.get("variant", "") or "")
    action = STRATEGIES.get(error_type, "switch_to_backup_endpoint")
    confidence = CONFIDENCE.get(error_type, 0.75)
    return {
        "agent": "fixer_b",
        "action": action,
        "confidence": confidence,
        "approach": "escape",
        "error_type": error_type,
        "variant": variant,
        "reasoning": "escape strategy: avoid problem -> use alternative",
        "philosophy": "don't fix, escape",
    }
