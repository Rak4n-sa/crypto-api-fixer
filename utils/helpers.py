"""
Helpers
دوال مساعدة مشتركة
"""

import hashlib
import random
import time
from typing import Any


def get_latency(start: float) -> float:
    return round((time.time() - start) * 1000, 2)


def exponential_backoff(attempt: int, base: float = 2.0, max_wait: float = 300) -> float:
    if not isinstance(attempt, int) or attempt < 0:
        attempt = 0
    try:
        wait = base ** min(attempt, 10)
    except Exception:
        wait = base
    return min(max_wait, wait + random.uniform(0, 1))


def is_fresh(timestamp: float, threshold: float = 5.0) -> bool:
    if not isinstance(timestamp, (int, float)):
        return False
    now = time.time()
    if timestamp > now:
        return False
    return (now - timestamp) <= threshold


def safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(str(value).replace(",", "").strip())
    except (ValueError, TypeError):
        return default


def get_agent_id(headers: Any) -> str:
    if hasattr(headers, "get"):
        raw = headers.get("X-Agent-ID") or headers.get("User-Agent", "unknown")
    else:
        raw = "unknown"
    return hashlib.sha256(str(raw).encode()).hexdigest()[:16]
