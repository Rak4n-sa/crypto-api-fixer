"""
JSON Repair Handler
يصلح JSON المكسور أو schema تغير أو fields ناقصة
بدون Claude API — حل مباشر فوري
"""

import time
import json
import re
from typing import Any, Dict, Optional

REQUIRED_FIELDS = ["symbol", "price"]

KNOWN_SCHEMA_MAPS = {
    "ticker.last_price": "price",
    "ticker.trading_pair": "symbol",
    "ticker.volume_24h": "volume",
    "data.amount": "price",
    "data.currency": "symbol",
    "result.last": "price",
    "result.pair": "symbol",
    "market.price": "price",
    "market.symbol": "symbol",
}


def handle(detection: Dict[str, Any], original_response: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    variant = detection.get("variant", "")
    data = original_response.get("data", {})
    raw = original_response.get("raw", "")

    if variant == "malformed_json":
        result = _handle_malformed(raw, data)
    elif variant == "schema_changed":
        result = _handle_schema_change(data)
    elif variant == "missing_fields":
        result = _handle_missing_fields(data)
    elif variant == "extra_nested":
        result = _handle_extra_nested(data)
    elif variant == "array_instead_object":
        result = _handle_array_response(data)
    else:
        result = _handle_generic(data)

    result["latency_ms"] = round((time.time() - start) * 1000, 2)
    result["handler"] = "json_repair"
    result["variant"] = variant
    return result


def _handle_malformed(raw: str, data: Any) -> Dict[str, Any]:
    if raw:
        fixed = _try_fix_json(raw)
        if fixed:
            return {"fixed": True, "action": "repaired_malformed_json", "data": fixed}
    if isinstance(data, dict) and data:
        return {"fixed": True, "action": "used_partial_data", "data": data, "warning": "fallback to partial data"}
    return {"fixed": False, "action": "rejected_malformed", "data": {}}


def _handle_schema_change(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {"fixed": False, "action": "invalid_schema_format", "data": {}}
    remapped = _remap_schema(data)
    if _has_required_fields(remapped):
        return {"fixed": True, "action": "remapped_schema", "data": remapped}
    flattened = _flatten(data)
    remapped = _remap_schema(flattened)
    if _has_required_fields(remapped):
        return {"fixed": True, "action": "flattened_and_remapped", "data": remapped}
    return {"fixed": False, "action": "unknown_schema", "data": flattened}


def _handle_missing_fields(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {"fixed": False, "action": "invalid_data", "data": {}}
    recovered = dict(data)
    missing = []
    for field in REQUIRED_FIELDS:
        if field not in recovered:
            val = _find_similar_field(data, field)
            if val is not None:
                recovered[field] = val
            else:
                missing.append(field)
    if not missing:
        return {"fixed": True, "action": "recovered_missing_fields", "data": recovered}
    if missing == ["price"] and "symbol" in recovered:
        return {
            "fixed": True,
            "action": "missing_price_degraded",
            "data": recovered,
            "price": None,
            "needs_price_refresh": True,
            "confidence": "low",
            "warning": "price missing — requires refresh",
        }
    if "symbol" in missing:
        return {"fixed": False, "action": "rejected_missing_symbol", "data": {}, "missing": missing}
    return {
        "fixed": True,
        "action": "partial_recovery",
        "data": recovered,
        "missing": missing,
        "confidence": "low",
        "warning": "partial data — missing fields: {}".format(missing),
    }


def _handle_extra_nested(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {"fixed": False, "action": "invalid_nested", "data": {}}
    flattened = _flatten(data)
    remapped = _remap_schema(flattened)
    if _has_required_fields(remapped):
        return {"fixed": True, "action": "flattened_nested", "data": remapped}
    return {"fixed": True, "action": "flattened_best_effort", "data": flattened}


def _handle_array_response(data: Any) -> Dict[str, Any]:
    if not isinstance(data, list) or not data:
        return {"fixed": False, "action": "invalid_array", "data": {}}
    for item in data:
        if isinstance(item, dict) and "price" in item:
            return {"fixed": True, "action": "picked_best_item", "data": item}
    merged = {}
    for item in data:
        if isinstance(item, dict):
            merged.update(item)
    if _has_required_fields(merged):
        return {"fixed": True, "action": "merged_array", "data": merged}
    return {"fixed": False, "action": "array_unusable", "data": {}}


def _handle_generic(data: Any) -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {"fixed": False, "action": "invalid_format", "data": {}}
    cleaned = {}
    for k, v in data.items():
        if v is None or v == "":
            continue
        if isinstance(v, str):
            num = _try_parse_number(v)
            cleaned[k] = num if num is not None else v
        else:
            cleaned[k] = v
    return {"fixed": True, "action": "generic_cleanup", "data": cleaned}


def _try_fix_json(raw: str) -> Optional[Dict[str, Any]]:
    raw = raw.strip()
    raw = re.sub(r',\s*([}\]])', r'\1', raw)
    raw = re.sub(r'([{,]\s*)([a-zA-Z0-9_]+)\s*:', r'\1"\2":', raw)
    try:
        return json.loads(raw)
    except Exception:
        pass
    match = re.search(r'\{.*\}', raw)
    if match:
        try:
            return json.loads(match.group())
        except Exception:
            pass
    return None


def _flatten(data: Any, prefix: str = "") -> Dict[str, Any]:
    result = {}
    if not isinstance(data, dict):
        return result
    for k, v in data.items():
        key = "{}.{}".format(prefix, k) if prefix else k
        if isinstance(v, dict):
            result.update(_flatten(v, key))
        else:
            result[key] = v
            result[k] = v
    return result


def _remap_schema(data: Dict[str, Any]) -> Dict[str, Any]:
    result = dict(data)
    for old, new in KNOWN_SCHEMA_MAPS.items():
        if old in data and new not in result:
            result[new] = data[old]
    return result


def _has_required_fields(data: Dict[str, Any]) -> bool:
    return all(k in data and data[k] is not None for k in REQUIRED_FIELDS)


def _find_similar_field(data: Dict[str, Any], target: str) -> Any:
    aliases = {
        "price": ["last_price", "close", "last", "rate", "amount"],
        "symbol": ["pair", "market", "instrument"],
    }
    for alias in aliases.get(target, []):
        if alias in data:
            return data[alias]
    return None


def _try_parse_number(val: str) -> Optional[float]:
    try:
        return float(val.replace(",", "").strip())
    except Exception:
        return None


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "../training")
    from broken_api_generator import generate_one

    print("⚡ JSON Repair Handler Test\n")
    fixed = 0
    total = 10
    for _ in range(total):
        error = generate_one("json_broken")
        detection = {"variant": error.get("variant", "")}
        result = handle(detection, error)
        icon = "✅" if result["fixed"] else "❌"
        print("{} variant={:<25} action={}".format(
            icon, result["variant"], result["action"]))
        if result["fixed"]:
            fixed += 1
    print("\n📊 Fixed: {}/{}".format(fixed, total))
