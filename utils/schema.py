"""
Schema
يعرّف شكل البيانات المتوقع
"""

from typing import Any, Dict

REQUIRED_PRICE_FIELDS = ["symbol", "price"]
REQUIRED_ORDER_FIELDS = ["symbol", "side", "quantity"]

EXCHANGE_SCHEMAS: Dict[str, Dict[str, str]] = {
    "binance":  {"price_field": "price",  "symbol_field": "symbol",   "ts_field": "time"},
    "coinbase": {"price_field": "amount", "symbol_field": "currency", "ts_field": "time"},
    "kraken":   {"price_field": "last",   "symbol_field": "pair",     "ts_field": "time"},
}


def is_valid_price_response(data: Dict[str, Any]) -> bool:
    if not isinstance(data, dict):
        return False
    if not all(f in data for f in REQUIRED_PRICE_FIELDS):
        return False
    try:
        float(data.get("price"))
        return True
    except (ValueError, TypeError):
        return False


def normalize(data: Dict[str, Any], exchange: str = "binance") -> Dict[str, Any]:
    if not isinstance(data, dict):
        return {}
    schema = EXCHANGE_SCHEMAS.get(exchange, EXCHANGE_SCHEMAS["binance"])
    price_field = schema.get("price_field", "price")
    symbol_field = schema.get("symbol_field", "symbol")
    result = dict(data)
    if price_field in data and "price" not in result:
        try:
            result["price"] = float(data[price_field])
        except (ValueError, TypeError):
            pass
    if symbol_field in data and "symbol" not in result:
        result["symbol"] = data[symbol_field]
    return result
