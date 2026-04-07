"""
Critic
ينتقد حلي fixer_a و fixer_b
يجد المشاكل فقط — بدون تصليح
"""

from typing import Any, Dict


def criticize(solution_a: Dict[str, Any], solution_b: Dict[str, Any], detection: Dict[str, Any]) -> Dict[str, Any]:
    error_type = str(detection.get("error_type", "") or "")
    financial_risk = bool(detection.get("financial_risk", False))

    critique_a = _critique_solution(solution_a, error_type, financial_risk)
    critique_b = _critique_solution(solution_b, error_type, financial_risk)

    return {
        "agent": "critic",
        "critique_a": critique_a,
        "critique_b": critique_b,
        "winner_hint": _hint_winner(critique_a, critique_b, financial_risk),
    }


def _critique_solution(solution: Dict[str, Any], error_type: str, financial_risk: bool) -> Dict[str, Any]:
    problems = []
    base_conf = solution.get("confidence", 0.5)
    try:
        score = float(base_conf)
    except (TypeError, ValueError):
        score = 0.5

    action = str(solution.get("action", "") or "")
    approach = str(solution.get("approach", "") or "")

    if financial_risk and "retry" in action.lower():
        problems.append("retrying during financial risk may cause duplicate trades")
        score -= 0.15

    if approach == "aggressive" and error_type in ("auth_error", "key_permission"):
        problems.append("aggressive approach on auth errors may trigger security lockout")
        score -= 0.1

    if "wait" in action.lower() and error_type in ("stale_data", "price_mismatch"):
        problems.append("waiting is too slow for time-sensitive price data")
        score -= 0.2

    if "backup" in action.lower() and error_type == "auth_error":
        problems.append("backup endpoint won't fix auth issue — same credentials needed")
        score -= 0.15

    if base_conf < 0.7:
        problems.append("low confidence ({}) — solution may fail".format(base_conf))
        score -= 0.1

    if "circuit_break" in action.lower() and error_type not in ("financial_risk", "websocket_dead"):
        problems.append("circuit breaker is too aggressive for this error type")
        score -= 0.1

    return {
        "action": action,
        "problems": problems,
        "problem_count": len(problems),
        "adjusted_score": round(max(0.0, min(1.0, score)), 3),
    }


def _hint_winner(critique_a: Dict[str, Any], critique_b: Dict[str, Any], financial_risk: bool) -> str:
    score_a = critique_a.get("adjusted_score", 0)
    score_b = critique_b.get("adjusted_score", 0)
    problems_a = critique_a.get("problem_count", 0)
    problems_b = critique_b.get("problem_count", 0)

    if financial_risk:
        if problems_a < problems_b:
            return "a"
        if problems_b < problems_a:
            return "b"

    if score_a > score_b:
        return "a"
    if score_b > score_a:
        return "b"
    return "tie"
