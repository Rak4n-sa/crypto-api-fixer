"""
Agents Loop
يشغّل الـ AutoReason loop كاملاً
fixer_a → fixer_b → critic → merger → judge
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'training'))

import time
import re
from typing import Any, Dict, Optional
from agents.fixer_a import propose as propose_a
from agents.fixer_b import propose as propose_b
from agents.critic import criticize
from agents.merger import merge
from agents.judge import judge

CLAUDE_API_KEY = os.getenv("ANTHROPIC_API_KEY", "")
CONFIDENCE_THRESHOLD = 0.65


def run(detection: Dict[str, Any], original_response: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()

    sol_a = propose_a(detection, original_response)
    sol_b = propose_b(detection, original_response)
    critique = criticize(sol_a, sol_b, detection)
    merged = merge(sol_a, sol_b, critique, detection)
    final = judge(sol_a, sol_b, merged, critique, detection, original_response)

    latency = round((time.time() - start) * 1000, 2)

    if not _validate_solution(final.get("action"), detection):
        return {
            "fixed": False,
            "source": "agents_loop",
            "action": "validation_failed",
            "confidence": 0.0,
            "price_usd": 0.007,
            "latency_ms": latency,
        }

    # لا تستخدم Claude إذا فيه خطر مالي
    if (
        final.get("confidence", 0) < CONFIDENCE_THRESHOLD
        and CLAUDE_API_KEY
        and not detection.get("financial_risk", False)
    ):
        claude_start = time.time()
        claude_result = _try_claude(detection, original_response)
        claude_latency = round((time.time() - claude_start) * 1000, 2)

        if claude_result and claude_result.get("action"):
            claude_result["source"] = "claude_api_last_resort"
            claude_result["latency_ms"] = latency + claude_latency
            return claude_result

    return {
        "fixed": True,
        "source": "agents_loop",
        "action": final.get("action"),
        "confidence": final.get("confidence"),
        "winner": final.get("winner_source"),
        "scores": final.get("all_scores"),
        "price_usd": 0.007,
        "latency_ms": latency,
    }


def _validate_solution(action: Any, detection: Dict[str, Any]) -> bool:
    if not action:
        return False
    if str(action) == "no_rule_found":
        return False
    return True


def _try_claude(detection: Dict[str, Any], original_response: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        import urllib.request
        import json

        error_type = str(detection.get("error_type", "") or "")
        variant = str(detection.get("variant", "") or "")

        prompt = (
            "You are a crypto API error fixer.\n"
            "Error type: {}\n"
            "Variant: {}\n"
            "Response data: {}\n\n"
            "Return ONLY a JSON object with:\n"
            "- action: string\n"
            "- confidence: float (0-1)\n"
            "- reasoning: string\n\n"
            "No explanation, just JSON."
        ).format(error_type, variant, original_response.get("data", {}))

        payload = json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 200,
            "messages": [{"role": "user", "content": prompt}]
        }).encode()

        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": CLAUDE_API_KEY,
                "anthropic-version": "2023-06-01",
            }
        )

        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            content = data.get("content", [])
            if not content:
                return None
            text = content[0].get("text", "")
            text = re.sub(r"```json|```", "", text).strip()
            try:
                result = json.loads(text)
            except Exception:
                return None
            return {
                "fixed": True,
                "action": result.get("action", "claude_fix"),
                "confidence": result.get("confidence", 0.8),
                "reasoning": result.get("reasoning", ""),
                "price_usd": 0.007,
            }
    except Exception:
        return None
