"""
x402 Payment Handler
دفع تلقائي عبر USDC على Base
"""

import hashlib
import os
import time
from collections import defaultdict
from typing import Any, Dict, Optional

WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "0xD338aF379E4cC2d71EacE60b02804A9D6d2504B3")
FREE_TIER_REQUESTS = 100
SIMPLE_PRICE = 0.003
COMPLEX_PRICE = 0.007
USDC_DECIMALS = 1_000_000
USDC_CONTRACT_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

_agent_usage: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
    "request_count": 0,
    "total_paid": 0.0,
    "free_remaining": FREE_TIER_REQUESTS,
    "first_seen": time.time(),
})


def check_payment(agent_id: str, price: float) -> Dict[str, Any]:
    usage = _agent_usage[agent_id]
    if usage["free_remaining"] > 0:
        return {
            "payment_required": False,
            "source": "free_tier",
            "free_remaining": usage["free_remaining"],
            "agent_id": agent_id,
        }
    return {
        "payment_required": True,
        "amount_usdc": price,
        "wallet": WALLET_ADDRESS,
        "network": "base",
        "currency": "USDC",
        "agent_id": agent_id,
        "payment_id": _generate_payment_id(agent_id, price),
    }


def process_payment(agent_id: str, price: float, tx_hash: Optional[str]) -> Dict[str, Any]:
    usage = _agent_usage[agent_id]
    if not tx_hash:
        return {"paid": False, "reason": "missing_tx_hash", "agent_id": agent_id}
    verified = _verify_payment(tx_hash, price)
    if verified:
        usage["request_count"] += 1
        usage["total_paid"] += price
        return {
            "paid": True,
            "amount_usdc": price,
            "tx_hash": tx_hash,
            "agent_id": agent_id,
            "total_paid": round(usage["total_paid"], 6),
        }
    return {"paid": False, "reason": "payment_not_verified", "agent_id": agent_id}


def payment_middleware(agent_id: str, price: float, tx_hash: Optional[str] = None) -> Dict[str, Any]:
    usage = _agent_usage[agent_id]
    check = check_payment(agent_id, price)

    if not check["payment_required"]:
        usage["free_remaining"] -= 1
        usage["request_count"] += 1
        return {"allowed": True, "source": "free_tier", "price": 0}

    if tx_hash:
        payment = process_payment(agent_id, price, tx_hash)
        if payment["paid"]:
            return {"allowed": True, "source": "paid", "price": price}

    return {
        "allowed": False,
        "source": "payment_required",
        "price": price,
        "payment_info": get_402_response(agent_id, price),
    }


def get_402_response(agent_id: str, price: float) -> Dict[str, Any]:
    return {
        "status": 402,
        "payment_required": True,
        "x402": {
            "version": "1",
            "accepts": [{
                "scheme": "exact",
                "network": "base",
                "maxAmountRequired": str(int(price * USDC_DECIMALS)),
                "resource": "/fix?agent={}".format(agent_id),
                "description": "Crypto API Fix — ${} USDC".format(price),
                "mimeType": "application/json",
                "payTo": WALLET_ADDRESS,
                "maxTimeoutSeconds": 60,
                "asset": USDC_CONTRACT_BASE,
            }]
        },
        "agent_message": "Payment required: ${} USDC on Base.".format(price),
    }


def get_agent_stats(agent_id: str) -> Dict[str, Any]:
    usage = _agent_usage[agent_id]
    return {
        "agent_id": agent_id,
        "request_count": usage["request_count"],
        "total_paid_usdc": round(usage["total_paid"], 6),
        "free_remaining": usage["free_remaining"],
        "member_since": usage["first_seen"],
    }


def get_revenue_stats() -> Dict[str, Any]:
    total_requests = sum(u["request_count"] for u in _agent_usage.values())
    total_revenue = sum(u["total_paid"] for u in _agent_usage.values())
    total_agents = len(_agent_usage)
    return {
        "total_agents": total_agents,
        "total_requests": total_requests,
        "total_revenue_usdc": round(total_revenue, 6),
        "avg_revenue_per_agent": round(total_revenue / max(total_agents, 1), 6),
    }


def _generate_payment_id(agent_id: str, price: float) -> str:
    raw = "{}:{}:{}".format(agent_id, price, time.time())
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _verify_payment(tx_hash: str, expected_price: float) -> bool:
    # Production: verify on Base blockchain
    return isinstance(tx_hash, str) and len(tx_hash) >= 10


if __name__ == "__main__":
    print("💰 x402 Payment Handler Test\n")
    print("=" * 50)

    agent = "test_bot_001"
    print("\n📦 Free Tier Test:")
    for i in range(3):
        result = payment_middleware(agent, SIMPLE_PRICE)
        stats = get_agent_stats(agent)
        print("   Request {}: allowed={} free_left={}".format(
            i+1, result["allowed"], stats["free_remaining"]))

    test_agent = "test_bot_002"
    _agent_usage[test_agent]["free_remaining"] = 0

    print("\n💳 Paid Request Test:")
    result = payment_middleware(test_agent, SIMPLE_PRICE)
    print("   Payment required: {}".format(not result["allowed"]))
    result = payment_middleware(test_agent, SIMPLE_PRICE, tx_hash="0xabcdef1234567890")
    print("   After payment: allowed={} source={}".format(result["allowed"], result["source"]))

    print("\n📊 Revenue Stats:")
    for k, v in get_revenue_stats().items():
        print("   {}: {}".format(k, v))
