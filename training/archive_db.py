"""
Archive DB
يحفظ كل حل ناجح من كل مستخدم حقيقي
Network effect — كل مستخدم يحسّن الأداة للكل
"""

import json
import time
import hashlib
from collections import defaultdict
from pathlib import Path
from typing import Any, Dict, List


ARCHIVE_PATH = Path(__file__).parent / "data" / "archive.json"


def _load_archive() -> Dict[str, Any]:
    if not ARCHIVE_PATH.exists():
        ARCHIVE_PATH.parent.mkdir(parents=True, exist_ok=True)
        return {
            "solutions": {},
            "stats": {"total_fixes": 0, "total_agents": 0, "total_saved_usd": 0.0}
        }
    try:
        with open(ARCHIVE_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {
            "solutions": {},
            "stats": {"total_fixes": 0, "total_agents": 0, "total_saved_usd": 0.0}
        }


def _save_archive(data: Dict[str, Any]) -> None:
    with open(ARCHIVE_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


def record_fix(
    agent_id: str,
    error_type: str,
    action: str,
    source: str,
    price: float,
    latency_ms: float,
    success: bool = True,
) -> None:
    try:
        archive = _load_archive()
        key = hashlib.md5("{}:{}".format(error_type, action).encode()).hexdigest()[:12]

        if key not in archive["solutions"]:
            archive["solutions"][key] = {
                "error_type": error_type,
                "action": action,
                "source": source,
                "fix_count": 0,
                "success_count": 0,
                "agents": [],
                "avg_latency_ms": 0.0,
                "first_seen": time.time(),
                "last_seen": time.time(),
            }

        sol = archive["solutions"][key]
        sol["fix_count"] += 1
        if success:
            sol["success_count"] += 1
        sol["last_seen"] = time.time()

        if agent_id not in sol["agents"]:
            sol["agents"].append(agent_id)

        count = sol["fix_count"]
        sol["avg_latency_ms"] = round(
            ((sol["avg_latency_ms"] * (count - 1)) + latency_ms) / count, 2)

        archive["stats"]["total_fixes"] += 1
        archive["stats"]["total_saved_usd"] = round(
            archive["stats"]["total_saved_usd"] + price, 6)

        _save_archive(archive)

    except Exception:
        pass


def get_best_solutions(error_type: str, limit: int = 5) -> List[Dict[str, Any]]:
    try:
        archive = _load_archive()
        matching = [
            s for s in archive["solutions"].values()
            if s["error_type"] == error_type and s["fix_count"] > 0
        ]
        matching.sort(
            key=lambda x: x["success_count"] / max(x["fix_count"], 1),
            reverse=True)
        return matching[:limit]
    except Exception:
        return []


def get_archive_stats() -> Dict[str, Any]:
    try:
        archive = _load_archive()
        stats = archive["stats"]
        solutions = archive["solutions"]
        unique_agents = set()
        for sol in solutions.values():
            unique_agents.update(sol.get("agents", []))
        return {
            "total_fixes": stats["total_fixes"],
            "unique_solutions": len(solutions),
            "unique_agents": len(unique_agents),
            "total_saved_usd": stats["total_saved_usd"],
            "top_error_types": _get_top_types(solutions),
        }
    except Exception:
        return {}


def get_agent_weekly_report(agent_id: str) -> Dict[str, Any]:
    try:
        archive = _load_archive()
        one_week_ago = time.time() - (7 * 24 * 3600)
        fixes = [
            s for s in archive["solutions"].values()
            if agent_id in s.get("agents", [])
            and s.get("last_seen", 0) > one_week_ago
        ]
        total_fixes = sum(s["fix_count"] for s in fixes)
        success_rate = sum(s["success_count"] for s in fixes) / max(total_fixes, 1)
        avg_latency = sum(s["avg_latency_ms"] for s in fixes) / max(len(fixes), 1)
        estimated_saved = total_fixes * 50
        return {
            "agent_id": agent_id,
            "period": "last_7_days",
            "total_fixes": total_fixes,
            "success_rate": round(success_rate * 100, 1),
            "avg_latency_ms": round(avg_latency, 2),
            "estimated_losses_prevented_usd": estimated_saved,
            "top_errors_fixed": [s["error_type"] for s in fixes[:3]],
        }
    except Exception:
        return {"agent_id": agent_id, "error": "no data"}


def _get_top_types(solutions: Dict[str, Any]) -> List[str]:
    counts: Dict[str, int] = defaultdict(int)
    for sol in solutions.values():
        counts[sol["error_type"]] += sol["fix_count"]
    sorted_types = sorted(counts.items(), key=lambda x: x[1], reverse=True)
    return [t[0] for t in sorted_types[:5]]
