"""
Pattern Matcher
يبحث في solution_db أولاً قبل ما يستدعي Claude API
"""

import time
from typing import Optional, Dict
from solution_db import get_solution, get_stats

MIN_SUCCESS_RATE = 0.70
MIN_USE_COUNT = 3
CACHE_TTL = 300


def match(error: Dict) -> Optional[Dict]:
    solution = get_solution(error)
    if solution:
        return {"found": True, "source": "exact_match", "solution": solution, "confidence": "high"}

    relaxed_error = {"error_type": error.get("error_type"), "variant": "", "status": error.get("status")}
    solution = get_solution(relaxed_error)
    if solution:
        return {"found": True, "source": "type_match", "solution": solution, "confidence": "medium"}

    status_error = {"error_type": "", "variant": "", "status": error.get("status")}
    solution = get_solution(status_error)
    if solution:
        return {"found": True, "source": "status_match", "solution": solution, "confidence": "low"}

    return None


def should_use_agents_loop(match_result: Optional[Dict]) -> bool:
    if match_result is None:
        return True
    if match_result.get("confidence") == "low":
        return True
    return False


def get_pricing(match_result: Optional[Dict]) -> float:
    if match_result and not should_use_agents_loop(match_result):
        return 0.003
    return 0.007


def get_db_coverage() -> Dict:
    stats = get_stats()
    total = stats.get("total", 0)
    by_type = stats.get("by_type", {})
    all_types = [
        "stale_data", "rate_limit", "endpoint_down", "unexpected_error",
        "price_mismatch", "json_broken", "auth_error", "financial_risk",
        "websocket_dead", "key_permission"
    ]
    covered = sum(1 for t in all_types if t in by_type)
    coverage_pct = round((covered / len(all_types)) * 100, 1)
    return {
        "total_solutions": total,
        "types_covered": covered,
        "total_types": len(all_types),
        "coverage_pct": coverage_pct,
        "avg_success_rate": stats.get("avg_success_rate", 0),
        "estimated_claude_savings_pct": round(coverage_pct * stats.get("avg_success_rate", 0), 1),
    }


if __name__ == "__main__":
    print("🔍 Pattern Matcher Test\n")

    test_cases = [
        {"error_type": "rate_limit", "variant": "429_with_retry", "status": 429},
        {"error_type": "rate_limit", "variant": "new_variant", "status": 429},
        {"error_type": "unknown_type", "variant": "unknown", "status": 429},
        {"error_type": "mystery_error", "variant": "unknown", "status": 999},
    ]

    for error in test_cases:
        result = match(error)
        price = get_pricing(result)
        if result:
            print("✅ {} | source={} | confidence={} | price=${}".format(
                error["error_type"], result["source"], result["confidence"], price))
        else:
            print("❌ {} | no match → agents loop | price=${}".format(
                error["error_type"], price))

    print("\n📊 DB Coverage:")
    coverage = get_db_coverage()
    for k, v in coverage.items():
        print("   {}: {}".format(k, v))
