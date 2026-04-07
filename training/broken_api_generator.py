"""
Broken API Generator
يولد آلاف الأخطاء الوهمية لتدريب الأداة
"""

import random
import time
from typing import Any, Dict, List
from collections import Counter

ERROR_TYPES = [
    "stale_data", "rate_limit", "endpoint_down", "unexpected_error",
    "price_mismatch", "json_broken", "auth_error", "financial_risk",
    "websocket_dead", "key_permission",
]

EXCHANGES = ["binance", "coinbase", "kraken", "bybit", "okx"]
PAIRS = ["BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT", "XRP/USDT"]

def gen_stale_data() -> Dict[str, Any]:
    delay = random.choice([10, 30, 60, 120, 300, 600])
    stale_time = time.time() - delay
    variants = [
        {"status": 200, "error_type": "stale_data", "variant": "old_timestamp",
         "delay_seconds": delay,
         "data": {"symbol": random.choice(PAIRS), "price": round(random.uniform(20000, 70000), 2),
                  "timestamp": stale_time, "exchange": random.choice(EXCHANGES)}},
        {"status": 200, "error_type": "stale_data", "variant": "missing_timestamp",
         "delay_seconds": delay,
         "data": {"symbol": random.choice(PAIRS), "price": round(random.uniform(20000, 70000), 2),
                  "exchange": random.choice(EXCHANGES)}},
        {"status": 200, "error_type": "stale_data", "variant": "wrong_format_timestamp",
         "delay_seconds": delay,
         "data": {"symbol": random.choice(PAIRS), "price": round(random.uniform(20000, 70000), 2),
                  "timestamp": "not-a-timestamp", "exchange": random.choice(EXCHANGES)}},
    ]
    return random.choice(variants)

def gen_rate_limit() -> Dict[str, Any]:
    variants = [
        {"status": 429, "error_type": "rate_limit", "variant": "429_with_retry",
         "headers": {"retry-after": random.randint(1, 60)},
         "data": {"error": "Too Many Requests", "msg": "Rate limit exceeded"}},
        {"status": 429, "error_type": "rate_limit", "variant": "429_no_retry",
         "headers": {}, "data": {"error": "Too Many Requests"}},
        {"status": 503, "error_type": "rate_limit", "variant": "503_overloaded",
         "headers": {}, "data": {"error": "Service Unavailable", "msg": "Server overloaded"}},
        {"status": 429, "error_type": "rate_limit", "variant": "429_ip_ban",
         "headers": {"retry-after": random.randint(300, 3600)},
         "data": {"error": "IP temporarily banned", "ban_duration": random.randint(300, 3600)}},
        {"status": 429, "error_type": "rate_limit", "variant": "429_weight_exceeded",
         "headers": {"x-mbx-used-weight": "1200", "x-mbx-used-weight-1m": "1200"},
         "data": {"code": -1003, "msg": "Way too many requests; IP banned"}},
    ]
    return random.choice(variants)

def gen_endpoint_down() -> Dict[str, Any]:
    variants = [
        {"status": 503, "error_type": "endpoint_down", "variant": "full_down",
         "data": {"error": "Service Unavailable"}},
        {"status": 504, "error_type": "endpoint_down", "variant": "gateway_timeout",
         "data": {"error": "Gateway Timeout"}},
        {"status": 502, "error_type": "endpoint_down", "variant": "bad_gateway",
         "data": {"error": "Bad Gateway"}},
        {"status": 0, "error_type": "endpoint_down", "variant": "connection_refused",
         "data": {"error": "Connection refused", "url": "https://api.binance.com"}},
        {"status": 0, "error_type": "endpoint_down", "variant": "dns_failed",
         "data": {"error": "DNS resolution failed"}},
    ]
    return random.choice(variants)

def gen_unexpected_error() -> Dict[str, Any]:
    variants = [
        {"status": 500, "error_type": "unexpected_error", "variant": "internal_server",
         "data": {"error": "Internal Server Error"}},
        {"status": 200, "error_type": "unexpected_error", "variant": "null_values",
         "data": {"symbol": random.choice(PAIRS), "price": None, "volume": None}},
        {"status": 200, "error_type": "unexpected_error", "variant": "wrong_types",
         "data": {"symbol": random.choice(PAIRS), "price": "not_a_number", "volume": "abc"}},
        {"status": 200, "error_type": "unexpected_error", "variant": "empty_response",
         "data": {}},
        {"status": 500, "error_type": "unexpected_error", "variant": "server_crash",
         "data": {"error": "Unexpected server error", "trace": "NullPointerException at line 42"}},
    ]
    return random.choice(variants)

def gen_price_mismatch() -> Dict[str, Any]:
    base_price = round(random.uniform(20000, 70000), 2)
    diff_pct = random.uniform(0.5, 5.0)
    variants = [
        {"status": 200, "error_type": "price_mismatch", "variant": "high_spread",
         "data": {"symbol": random.choice(PAIRS),
                  "prices": {"binance": base_price,
                             "coinbase": round(base_price * (1 + diff_pct / 100), 2),
                             "kraken": round(base_price * (1 - diff_pct / 200), 2)},
                  "spread_pct": round(diff_pct, 2)}},
        {"status": 200, "error_type": "price_mismatch", "variant": "outlier_price",
         "data": {"symbol": random.choice(PAIRS),
                  "prices": {"binance": base_price, "coinbase": base_price,
                             "bybit": round(base_price * random.uniform(1.05, 1.15), 2)},
                  "spread_pct": round(diff_pct * 3, 2)}},
    ]
    return random.choice(variants)

def gen_json_broken() -> Dict[str, Any]:
    variants = [
        {"status": 200, "error_type": "json_broken", "variant": "malformed_json",
         "raw": '{"price": 45000, "symbol": "BTC/USDT", "volume":}'},
        {"status": 200, "error_type": "json_broken", "variant": "schema_changed",
         "data": {"ticker": {"last_price": 45000, "trading_pair": "BTC/USDT"}}},
        {"status": 200, "error_type": "json_broken", "variant": "missing_fields",
         "data": {"symbol": random.choice(PAIRS)}},
        {"status": 200, "error_type": "json_broken", "variant": "extra_nested",
         "data": {"result": {"data": {"market": {"price": 45000}}}}},
        {"status": 200, "error_type": "json_broken", "variant": "array_instead_object",
         "data": [{"symbol": "BTC/USDT", "price": 45000}]},
    ]
    return random.choice(variants)

def gen_auth_error() -> Dict[str, Any]:
    variants = [
        {"status": 401, "error_type": "auth_error", "variant": "invalid_api_key",
         "data": {"code": -2014, "msg": "API-key format invalid"}},
        {"status": 403, "error_type": "auth_error", "variant": "signature_mismatch",
         "data": {"code": -1022, "msg": "Signature for this request is not valid"}},
        {"status": 401, "error_type": "auth_error", "variant": "expired_key",
         "data": {"code": -1099, "msg": "Not found, unauthenticated, or unauthorized"}},
        {"status": 403, "error_type": "auth_error", "variant": "ip_not_whitelisted",
         "data": {"code": -2015, "msg": "Invalid API-key, IP, or permissions for action"}},
        {"status": 401, "error_type": "auth_error", "variant": "timestamp_out_of_sync",
         "data": {"code": -1021, "msg": "Timestamp for this request is outside of the recvWindow"}},
    ]
    return random.choice(variants)

def gen_financial_risk() -> Dict[str, Any]:
    variants = [
        {"status": 200, "error_type": "financial_risk", "variant": "price_spike",
         "data": {"symbol": random.choice(PAIRS), "current_price": 45000,
                  "bot_last_price": 44000, "change_pct": random.uniform(3, 15), "risk": "high"}},
        {"status": 200, "error_type": "financial_risk", "variant": "low_liquidity",
         "data": {"symbol": random.choice(PAIRS), "order_book_depth": random.randint(1, 5),
                  "required_depth": 20, "risk": "slippage_likely"}},
        {"status": 200, "error_type": "financial_risk", "variant": "latency_spike",
         "data": {"latency_ms": random.randint(500, 3000), "threshold_ms": 100,
                  "risk": "stale_execution"}},
    ]
    return random.choice(variants)

def gen_websocket_dead() -> Dict[str, Any]:
    variants = [
        {"status": 0, "error_type": "websocket_dead", "variant": "silent_disconnect",
         "data": {"last_message_ago_seconds": random.randint(30, 300), "connected": True}},
        {"status": 0, "error_type": "websocket_dead", "variant": "no_heartbeat",
         "data": {"heartbeat_expected_every": 30, "last_heartbeat_ago": random.randint(60, 600)}},
        {"status": 0, "error_type": "websocket_dead", "variant": "stale_stream",
         "data": {"stream_active": True, "last_data_timestamp": time.time() - random.randint(60, 300)}},
    ]
    return random.choice(variants)

def gen_key_permission() -> Dict[str, Any]:
    variants = [
        {"status": 403, "error_type": "key_permission", "variant": "no_trade_permission",
         "data": {"msg": "This key does not have permission to trade", "required": "TRADE"}},
        {"status": 403, "error_type": "key_permission", "variant": "withdrawal_enabled",
         "data": {"msg": "WARNING: Withdrawal permission is enabled", "risk": "critical"}},
        {"status": 403, "error_type": "key_permission", "variant": "read_only",
         "data": {"msg": "API key is read-only", "required_permissions": ["TRADE", "READ"]}},
    ]
    return random.choice(variants)

GENERATORS: Dict[str, Any] = {
    "stale_data": gen_stale_data,
    "rate_limit": gen_rate_limit,
    "endpoint_down": gen_endpoint_down,
    "unexpected_error": gen_unexpected_error,
    "price_mismatch": gen_price_mismatch,
    "json_broken": gen_json_broken,
    "auth_error": gen_auth_error,
    "financial_risk": gen_financial_risk,
    "websocket_dead": gen_websocket_dead,
    "key_permission": gen_key_permission,
}

def generate_one(error_type=None):
    # type: (str) -> Dict[str, Any]
    if error_type is None:
        error_type = random.choice(ERROR_TYPES)
    return GENERATORS[error_type]()

def generate_batch(count=1000, balanced=True):
    # type: (int, bool) -> List[Dict[str, Any]]
    results = []
    if balanced:
        per_type = count // len(ERROR_TYPES)
        for error_type in ERROR_TYPES:
            for _ in range(per_type):
                results.append(generate_one(error_type))
    else:
        for _ in range(count):
            results.append(generate_one())
    random.shuffle(results)
    return results

def generate_stress_test(count=10000):
    # type: (int) -> List[Dict[str, Any]]
    return generate_batch(count, balanced=True)

if __name__ == "__main__":
    print("🔧 Broken API Generator\n")
    for error_type in ERROR_TYPES:
        sample = generate_one(error_type)
        print("✅ {}: status={} | variant={}".format(
            error_type, sample.get("status"), sample.get("variant")))
    print("\n📦 Generating 1000 samples...")
    batch = generate_batch(1000)
    print("✅ Generated {} samples".format(len(batch)))
    counts = Counter(s["error_type"] for s in batch)
    print("\n📊 Distribution:")
    for k, v in sorted(counts.items()):
        print("   {}: {}".format(k, v))
