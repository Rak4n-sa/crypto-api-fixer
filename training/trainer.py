"""
Trainer
يشغّل التدريب الكامل
"""

import time
import random
from typing import Tuple, Dict
from broken_api_generator import generate_batch, ERROR_TYPES
from solution_db import save_solution, get_stats, clear_db
from pattern_matcher import get_db_coverage

SOLUTIONS = {
    "stale_data": [
        {"action": "reject_and_refetch", "reason": "timestamp too old", "retry": True},
        {"action": "use_backup_source", "reason": "missing_timestamp", "retry": True},
        {"action": "reject_invalid_timestamp", "reason": "wrong format", "retry": True},
    ],
    "rate_limit": [
        {"action": "wait_and_retry", "wait_seconds": 30, "use_backup_key": False},
        {"action": "wait_and_retry", "wait_seconds": 60, "use_backup_key": False},
        {"action": "switch_to_backup_endpoint", "wait_seconds": 0},
        {"action": "wait_and_retry", "wait_seconds": 300, "rotate_ip": True},
        {"action": "reduce_request_weight", "wait_seconds": 60},
    ],
    "endpoint_down": [
        {"action": "switch_to_backup_endpoint", "backup": "mirror_api"},
        {"action": "switch_to_backup_endpoint", "backup": "cdn_mirror"},
        {"action": "switch_to_backup_endpoint", "backup": "regional_endpoint"},
        {"action": "wait_and_retry", "wait_seconds": 10, "max_retries": 3},
        {"action": "switch_to_backup_endpoint", "backup": "websocket_fallback"},
        {"action": "failover_to_secondary_region", "retry": True},
        {"action": "use_cached_response_temporarily", "retry": True},
        {"action": "switch_protocol_http_ws", "retry": True},
        {"action": "switch_dns_provider", "retry": True},
        {"action": "route_through_proxy_gateway", "retry": True},
        {"action": "use_aggregator_api", "retry": True},
    ],
    "unexpected_error": [
        {"action": "retry_once", "log": True},
        {"action": "return_null_safe", "log": True},
        {"action": "reject_null_values", "log": True},
        {"action": "reject_invalid_types", "log": True},
        {"action": "retry_once", "log": True, "alert": True},
    ],
    "price_mismatch": [
        {"action": "use_median_price", "sources": ["binance", "coinbase", "kraken"]},
        {"action": "exclude_outlier_use_average", "threshold_pct": 3.0},
    ],
    "json_broken": [
        {"action": "reject_malformed", "log": True, "retry": True},
        {"action": "remap_nested_schema", "mapping": {"ticker.last_price": "price"}},
        {"action": "reject_missing_required_fields", "required": ["price", "symbol"]},
        {"action": "flatten_deep_nested", "depth": 4},
        {"action": "extract_from_array_first_item"},
        {"action": "auto_fix_json_syntax", "retry": True},
        {"action": "fill_missing_fields_with_defaults", "defaults": {"price": 0.0}},
        {"action": "coerce_types_to_expected", "retry": True},
        {"action": "unwrap_nested_response_layers", "retry": True},
        {"action": "convert_array_to_object_first_entry", "retry": True},
        {"action": "drop_invalid_fields", "retry": True},
        {"action": "infer_schema_and_rebuild", "retry": True},
    ],
    "auth_error": [
        {"action": "reformat_api_key", "retry": True},
        {"action": "recalculate_signature", "retry": True},
        {"action": "sync_timestamp", "retry": True},
        {"action": "use_backup_api_key", "retry": True, "degraded_mode": True},
        {"action": "switch_to_read_only_mode", "retry": False, "degraded_mode": True},
        {"action": "route_through_proxy_ip", "retry": True, "degraded_mode": True},
        {"action": "fallback_to_public_endpoints", "retry": True, "degraded_mode": True},
        {"action": "alert_key_expired", "retry": False},
        {"action": "alert_ip_not_whitelisted", "retry": False},
    ],
    "financial_risk": [
        {"action": "pause_trading", "reason": "price_spike", "alert": True},
        {"action": "pause_trading", "reason": "low_liquidity", "alert": True},
        {"action": "pause_trading", "reason": "high_latency", "alert": True},
    ],
    "websocket_dead": [
        {"action": "reconnect_websocket", "reason": "silent_disconnect"},
        {"action": "reconnect_websocket", "reason": "no_heartbeat"},
        {"action": "reconnect_websocket", "reason": "stale_stream"},
    ],
    "key_permission": [
        {"action": "alert_missing_trade_permission", "retry": False},
        {"action": "alert_withdrawal_enabled", "severity": "critical", "retry": False},
        {"action": "alert_read_only_key", "retry": False},
    ],
}

SUCCESS_RATES = {
    "stale_data": 0.95,
    "rate_limit": 0.90,
    "endpoint_down": 0.92,
    "unexpected_error": 0.80,
    "price_mismatch": 0.92,
    "json_broken": 0.88,
    "auth_error": 0.88,
    "financial_risk": 0.98,
    "websocket_dead": 0.88,
    "key_permission": 0.95,
}


def _get_solution_for(error):
    # type: (Dict) -> Tuple[Dict, bool]
    error_type = error.get("error_type", "")
    solutions = SOLUTIONS.get(error_type, [])
    if not solutions:
        return {"action": "unknown_error", "log": True}, False
    solution = random.choice(solutions)
    success_rate = SUCCESS_RATES.get(error_type, 0.75)
    success = random.random() < success_rate
    return solution, success


def run_training(count=1000, reset_db=False, verbose=True):
    # type: (int, bool, bool) -> Dict
    if reset_db:
        clear_db()
        if verbose:
            print("🗑️  Database cleared\n")

    if verbose:
        print("🚀 Starting training with {} samples...\n".format(count))

    start_time = time.time()
    errors = generate_batch(count, balanced=True)
    results = {t: {"total": 0, "success": 0} for t in ERROR_TYPES}
    saved = 0

    for i, error in enumerate(errors):
        solution, success = _get_solution_for(error)
        save_solution(error, solution, success)
        error_type = error.get("error_type", "unknown")
        results[error_type]["total"] += 1
        if success:
            results[error_type]["success"] += 1
        saved += 1
        if verbose and (i + 1) % 200 == 0:
            print("   ⏳ {}/{} processed...".format(i + 1, count))

    elapsed = round(time.time() - start_time, 2)
    report = {"total_trained": saved, "elapsed_seconds": elapsed, "by_type": {}}

    if verbose:
        print("\n✅ Training complete in {}s\n".format(elapsed))
        print("{:<25} {:>7} {:>9} {:>7}".format("Type", "Total", "Success", "Rate"))
        print("-" * 52)

    for error_type, data in results.items():
        total = data["total"]
        success = data["success"]
        rate = round(success / total, 3) if total > 0 else 0
        report["by_type"][error_type] = {"total": total, "success": success, "rate": rate}
        if verbose:
            bar = "█" * int(rate * 20)
            print("{:<25} {:>7} {:>9} {:>6.1f}%  {}".format(
                error_type, total, success, rate * 100, bar))

    coverage = get_db_coverage()
    report["coverage"] = coverage

    if verbose:
        print("\n📈 DB Coverage: {}/{}".format(
            coverage["types_covered"], coverage["total_types"]))
        print("📊 Avg success rate: {}".format(coverage["avg_success_rate"]))
        print("💰 Estimated Claude savings: {}%".format(
            coverage["estimated_claude_savings_pct"]))

    return report


if __name__ == "__main__":
    print("🎓 Crypto API Fixer — Trainer\n")
    print("=" * 52)
    report = run_training(count=1000, reset_db=True, verbose=True)
    print("\n✅ Done! {} solutions saved to DB".format(report["total_trained"]))
