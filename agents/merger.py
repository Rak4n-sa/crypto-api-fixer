"""
Merger
يدمج أفضل أجزاء من حلي fixer_a و fixer_b
بناءً على نتيجة الـ critic
"""

from typing import Any, Dict


def merge(solution_a: Dict[str, Any], solution_b: Dict[str, Any], critique: Dict[str, Any], detection: Dict[str, Any]) -> Dict[str, Any]:
    winner_hint = str(critique.get("winner_hint", "tie") or "tie")
    critique_a = critique.get("critique_a", {}) or {}
    critique_b = critique.get("critique_b", {}) or {}
    financial_risk = bool(detection.get("financial_risk", False))

    score_a = _safe_float(critique_a.get("adjusted_score", 0.5))
    score_b = _safe_float(critique_b.get("adjusted_score", 0.5))

    action_a = str(solution_a.get("action", "") or "")
    action_b = str(solution_b.get("action", "") or "")

    if winner_hint == "a" and score_a > score_b + 0.15:
        return _build_result(solution_a, "solution_a_dominant", score_a)

    if winner_hint == "b" and score_b > score_a + 0.15:
        return _build_result(solution_b, "solution_b_dominant", score_b)

    merged_action = _merge_actions(action_a, action_b, winner_hint, financial_risk)
    merged_confidence = round((score_a + score_b) / 2, 3)

    return {
        "agent": "merger",
        "action": merged_action,
        "confidence": merged_confidence,
        "source_a": action_a,
        "source_b": action_b,
        "merge_strategy": "weighted_blend",
        "financial_risk": financial_risk,
    }


def _merge_actions(action_a: str, action_b: str, winner: str, financial_risk: bool) -> str:
    action_a = action_a or ""
    action_b = action_b or ""
    a_lower = action_a.lower()
    b_lower = action_b.lower()

    if financial_risk:
        safe_keywords = ["pause", "stop", "circuit", "alert", "reduce"]
        a_safe = any(k in a_lower for k in safe_keywords)
        b_safe = any(k in b_lower for k in safe_keywords)
        if a_safe and not b_safe:
            return action_a
        if b_safe and not a_safe:
            return action_b

    if winner == "a":
        return action_a
    if winner == "b":
        return action_b

    if not action_a and action_b:
        return action_b
    if not action_b and action_a:
        return action_a

    return action_a if len(action_a) <= len(action_b) else action_b


def _build_result(solution: Dict[str, Any], strategy: str, confidence: float) -> Dict[str, Any]:
    return {
        "agent": "merger",
        "action": solution.get("action"),
        "confidence": round(_safe_float(confidence), 3),
        "merge_strategy": strategy,
        "source": solution.get("agent"),
    }


def _safe_float(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.5
