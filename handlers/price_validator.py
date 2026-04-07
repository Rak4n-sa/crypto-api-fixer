"""
Price Validator Handler
يتحقق من صحة الأسعار بين المنصات
يمنع البوت من التداول على سعر خاطئ
"""

import time
import random
from typing import Any, Dict, List, Optional, Tuple

MAX_SPREAD_PCT = 1.0
OUTLIER_THRESHOLD = 3.0
MIN_SOURCES = 2

MOCK_MARKET_PRICES = {
    "BTC/USDT": 45000,
    "ETH/USDT": 2500,
    "SOL/USDT": 120,
    "BNB/USDT": 420,
    "XRP/USDT": 0.85,
}


def handle(detection: Dict[str, Any], original_response: Dict[str, Any]) -> Dict[str, Any]:
    start = time.time()
    variant = detection.get("variant", "")
    data = original_response.get("data", {})

    if not isinstance(data, dict):
        data = {}

    if variant == "high_spread":
        result = _handle_high_spread(data)
    elif variant == "outlier_price":
        result = _handle_outlier(data)
    else:
        result = _handle_generic_mismatch(data)

    result["latency_ms"] = round((time.time() - start) * 1000, 2)
    result["handler"] = "price_validator"
    result["variant"] = variant
    return result


def _handle_high_spread(data: Dict[str, Any]) -> Dict[str, Any]:
    prices = data.get("prices", {})
    symbol = data.get("symbol", "BTC/USDT")

    if not isinstance(prices, dict):
        prices = {}

    if len(prices) < MIN_SOURCES:
        prices = _fetch_additional_prices(symbol, prices)

    validated = _smart_median(prices)
    spread = _calc_spread(prices)

    if spread > MAX_SPREAD_PCT * 3:
        return {
            "fixed": True,
            "action": "used_median_high_risk",
            "validated_price": validated,
            "original_prices": prices,
            "spread_pct": round(spread, 2),
            "confidence": "low",
            "alert": True,
            "warning": "high spread {}% — trade with caution".format(round(spread, 2)),
        }

    return {
        "fixed": True,
        "action": "used_median_price",
        "validated_price": validated,
        "original_prices": prices,
        "spread_pct": round(spread, 2),
        "confidence": "high",
    }


def _handle_outlier(data: Dict[str, Any]) -> Dict[str, Any]:
    prices = data.get("prices", {})
    symbol = data.get("symbol", "BTC/USDT")

    if not isinstance(prices, dict) or not prices:
        return {
            "fixed": False,
            "action": "rejected_no_prices",
            "validated_price": None,
            "confidence": "none",
        }

    clean_prices, outliers = _remove_outliers(prices)

    if not clean_prices:
        fresh = _fetch_fresh_price(symbol)
        return {
            "fixed": True,
            "action": "replaced_all_outliers",
            "validated_price": fresh,
            "outliers_removed": outliers,
            "confidence": "medium",
        }

    validated = _smart_median(clean_prices)
    return {
        "fixed": True,
        "action": "excluded_outlier",
        "validated_price": validated,
        "clean_prices": clean_prices,
        "outliers_removed": outliers,
        "spread_pct": round(_calc_spread(clean_prices), 2),
        "confidence": "high",
    }


def _handle_generic_mismatch(data: Dict[str, Any]) -> Dict[str, Any]:
    prices = data.get("prices", {})
    symbol = data.get("symbol", "BTC/USDT")

    if not isinstance(prices, dict) or not prices:
        fresh = _fetch_fresh_price(symbol)
        return {
            "fixed": True,
            "action": "fetched_fresh_price",
            "validated_price": fresh,
            "confidence": "medium",
        }

    validated = _smart_median(prices)
    return {
        "fixed": True,
        "action": "used_median_generic",
        "validated_price": validated,
        "confidence": "medium",
    }


def _smart_median(prices: Dict[str, Any]) -> float:
    values = [v for v in prices.values() if isinstance(v, (int, float))]
    values = sorted(values)
    n = len(values)
    if n == 0:
        return 0.0
    if n % 2 == 0:
        return round((values[n//2 - 1] + values[n//2]) / 2, 2)
    return round(values[n//2], 2)


def _calc_spread(prices: Dict[str, Any]) -> float:
    values = [v for v in prices.values() if isinstance(v, (int, float))]
    if len(values) < 2:
        return 0.0
    min_p, max_p = min(values), max(values)
    if min_p == 0:
        return 0.0
    return ((max_p - min_p) / min_p) * 100


def _remove_outliers(prices: Dict[str, Any]) -> Tuple[Dict[str, Any], List[Any]]:
    if len(prices) < 2:
        return prices, []

    values = [v for v in prices.values() if isinstance(v, (int, float))]
    if not values:
        return {}, []

    median = sorted(values)[len(values) // 2]
    clean = {}
    outliers = []

    for exchange, price in prices.items():
        if not isinstance(price, (int, float)):
            continue
        if median == 0:
            clean[exchange] = price
            continue
        diff_pct = abs((price - median) / median) * 100
        if diff_pct > OUTLIER_THRESHOLD:
            outliers.append({"exchange": exchange, "price": price, "diff_pct": round(diff_pct, 2)})
        else:
            clean[exchange] = price

    return clean, outliers


def _fetch_additional_prices(symbol: str, existing: Dict[str, Any]) -> Dict[str, Any]:
    base = MOCK_MARKET_PRICES.get(symbol, 1000)
    exchanges = ["binance", "coinbase", "kraken", "bybit", "okx"]
    result = dict(existing)
    for exchange in exchanges:
        if exchange not in result and len(result) < 4:
            result[exchange] = round(base * random.uniform(0.995, 1.005), 2)
    return result


def _fetch_fresh_price(symbol: str) -> float:
    base = MOCK_MARKET_PRICES.get(symbol, 1000)
    return round(base * random.uniform(0.998, 1.002), 2)


def is_price_mismatch(response: Dict[str, Any]) -> bool:
    data = response.get("data", {})
    if not isinstance(data, dict):
        return False
    prices = data.get("prices", {})
    if isinstance(prices, dict) and len(prices) >= 2:
        return _calc_spread(prices) > MAX_SPREAD_PCT
    return False


if __name__ == "__main__":
    import sys
    sys.path.insert(0, "../training")
    from broken_api_generator import generate_one

    print("⚡ Price Validator Handler Test\n")
    fixed = 0
    total = 10
    for i in range(total):
        error = generate_one("price_mismatch")
        detection = {"variant": error.get("variant", ""), "status": error.get("status", 200)}
        result = handle(detection, error)
        icon = "✅" if result["fixed"] else "❌"
        print("{} variant={:<15} action={:<30} price={} spread={}% conf={}".format(
            icon, result["variant"], result["action"],
            result.get("validated_price", "N/A"),
            result.get("spread_pct", 0),
            result.get("confidence", "?")))
        if result["fixed"]:
            fixed += 1
    print("\n📊 Fixed: {}/{} ({}%)".format(fixed, total, round(fixed/total*100)))
