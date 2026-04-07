"""
Judge
يختار الحل النهائي — يعتمد على DB history + critique
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'training'))

from typing import Any, Dict
from solution_db import save_solution, _load_db


def judge(sol_a, sol_b, merged, critique, detection, original_response):
    financial_risk = bool(detection.get("financial_risk", False))
    candidates = [c for c in [sol_a, sol_b, merged] if isinstance(c, dict)]

    if not candidates:
        return {
            "agent": "judge",
            "action": "no_valid_solution",
            "confidence": 0.0,
            "winner_source": "none",
            "financial_risk": financial_risk,
        }

    scores = [_score(c, critique, detection) for c in candidates]
    best_idx = scores.index(max(scores))
    winner = candidates[best_idx]

    final = {
        "agent": "judge",
        "action": winner.get("action"),
        "confidence": round(scores[best_idx], 3),
        "winner_source": winner.get("agent", "unknown"),
        "all_scores": {
            "fixer_a": round(_safe_score(sol_a, critique, detection), 3),
            "fixer_b": round(_safe_score(sol_b, critique, detection), 3),
            "merger":  round(_safe_score(merged, critique, detection), 3),
        },
        "financial_risk": financial_risk,
    }

    _save_to_db(detection, final, original_response)
    return final


def _safe_score(solution: Any, critique: Dict[str, Any], detection: Dict[str, Any]) -> float:
    if not isinstance(solution, dict):
        return 0.0
    return _score(solution, critique, detection)


def _score(solution: Dict[str, Any], critique: Dict[str, Any], detection: Dict[str, Any]) -> float:
    agent = str(solution.get("agent", "") or "")
    base_confidence = solution.get("confidence", 0.5)
    try:
        base_confidence = float(base_confidence)
    except (TypeError, ValueError):
        base_confidence = 0.5

    if agent == "fixer_a":
        adjusted = critique.get("critique_a", {}).get("adjusted_score", base_confidence)
    elif agent == "fixer_b":
        adjusted = critique.get("critique_b", {}).get("adjusted_score", base_confidence)
    else:
        score_a = critique.get("critique_a", {}).get("adjusted_score", 0.5)
        score_b = critique.get("critique_b", {}).get("adjusted_score", 0.5)
        adjusted = (score_a + score_b) / 2
        if solution.get("agent") == "merger":
            adjusted += 0.03

    try:
        adjusted = float(adjusted)
    except (TypeError, ValueError):
        adjusted = 0.5

    success_rate = _get_historical_success(
        str(detection.get("error_type", "") or ""),
        str(solution.get("action", "") or "")
    )

    return round(min(1.0, (0.6 * adjusted) + (0.4 * success_rate)), 3)


def _get_historical_success(error_type: str, action: str) -> float:
    try:
        db = _load_db()
        matching = [
            r for r in db.values()
            if r.get("error_type") == error_type
            and r.get("solution", {}).get("action") == action
        ]
        if not matching:
            return 0.5
        return round(sum(r.get("success_rate", 0.5) for r in matching) / len(matching), 3)
    except Exception:
        return 0.5


def _save_to_db(detection: Dict[str, Any], final: Dict[str, Any], original_response: Dict[str, Any]) -> None:
    try:
        error = {
            "error_type": detection.get("error_type"),
            "variant": detection.get("variant"),
            "status": detection.get("status", 0),
        }
        solution = {
            "action": final.get("action"),
            "confidence": final.get("confidence"),
            "source": "agents_loop",
        }
        save_solution(error, solution, final.get("confidence", 0) >= 0.7)
    except Exception:
        pass
