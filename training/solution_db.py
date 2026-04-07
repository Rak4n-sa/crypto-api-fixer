"""
Solution DB
يحفظ المشكلة + الحل الناجح ويسترجعها لاحقاً
بدون Claude API — يعتمد على الحلول المحفوظة مسبقاً
"""

import json
import os
import time
import random
import hashlib
from pathlib import Path
from typing import Any, Dict, Optional

DB_PATH = Path(__file__).parent / "data" / "solutions.json"

def _load_db() -> Dict[str, Any]:
    if not DB_PATH.exists():
        DB_PATH.parent.mkdir(parents=True, exist_ok=True)
        return {}
    with open(DB_PATH, "r") as f:
        return json.load(f)

def _save_db(db: Dict[str, Any]) -> None:
    with open(DB_PATH, "w") as f:
        json.dump(db, f, indent=2)

def _make_key(error: Dict[str, Any]) -> str:
    parts = [
        str(error.get("error_type", "")),
        str(error.get("variant", "")),
        str(error.get("status", "")),
    ]
    raw = "|".join(parts)
    return hashlib.md5(raw.encode()).hexdigest()

def _calc_success_rate(existing: Optional[Dict[str, Any]], new_success: bool) -> float:
    if not existing:
        return 1.0 if new_success else 0.0
    old_rate = existing.get("success_rate", 1.0)
    count = existing.get("use_count", 1)
    new_rate = ((old_rate * count) + (1.0 if new_success else 0.0)) / (count + 1)
    return round(new_rate, 3)

def save_solution(error: Dict[str, Any], solution: Dict[str, Any], success: bool = True) -> str:
    db = _load_db()
    key = _make_key(error)
    record = {
        "error_type": error.get("error_type"),
        "variant": error.get("variant"),
        "status": error.get("status"),
        "solution": solution,
        "success": success,
        "saved_at": time.time(),
        "use_count": db.get(key, {}).get("use_count", 0),
        "success_rate": _calc_success_rate(db.get(key), success),
    }
    db[key] = record
    _save_db(db)
    return key

def get_solution(error: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    db = _load_db()
    key = _make_key(error)
    record = db.get(key)
    if record and record.get("success") and record.get("success_rate", 0) >= 0.7:
        record["use_count"] = record.get("use_count", 0) + 1
        db[key] = record
        _save_db(db)
        return record["solution"]
    return None

def mark_solution_result(error: Dict[str, Any], success: bool) -> None:
    db = _load_db()
    key = _make_key(error)
    if key in db:
        db[key]["success_rate"] = _calc_success_rate(db[key], success)
        db[key]["use_count"] = db[key].get("use_count", 0) + 1
        _save_db(db)

def get_stats() -> Dict[str, Any]:
    db = _load_db()
    if not db:
        return {"total": 0, "by_type": {}, "avg_success_rate": 0}
    by_type = {}
    total_success = 0
    for record in db.values():
        error_type = record.get("error_type", "unknown")
        by_type[error_type] = by_type.get(error_type, 0) + 1
        total_success += record.get("success_rate", 0)
    return {
        "total": len(db),
        "by_type": by_type,
        "avg_success_rate": round(total_success / len(db), 3),
    }

def clear_db() -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
        print("🗑️  Database cleared")

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(Path(__file__).parent))

    print("💾 Solution DB Test\n")
    clear_db()

    test_error = {"error_type": "rate_limit", "variant": "429_with_retry", "status": 429}
    test_solution = {"action": "wait_and_retry", "wait_seconds": 30, "use_backup_key": False}

    key = save_solution(test_error, test_solution, success=True)
    print("✅ Saved solution | key: {}...".format(key[:8]))

    found = get_solution(test_error)
    print("✅ Retrieved: {}".format(found))

    unknown_error = {"error_type": "stale_data", "variant": "old_timestamp", "status": 200}
    not_found = get_solution(unknown_error)
    print("✅ Unknown error returns: {}".format(not_found))

    try:
        from broken_api_generator import generate_batch
        batch = generate_batch(50)
        for error in batch:
            mock_solution = {"action": "fix_{}".format(error["error_type"]), "auto": True}
            save_solution(error, mock_solution, success=random.choice([True, True, True, False]))
    except ImportError:
        print("⚠️ broken_api_generator not found, skipping batch save")

    stats = get_stats()
    print("\n📊 Stats:")
    print("   Total solutions: {}".format(stats["total"]))
    print("   Avg success rate: {}".format(stats["avg_success_rate"]))
    print("   By type: {}".format(stats["by_type"]))
