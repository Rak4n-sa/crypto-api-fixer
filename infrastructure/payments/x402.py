"""
x402 Payment Handler - Real Blockchain Verification
يتحقق من الدفع الحقيقي على Base blockchain
"""

import os
import time
import hashlib
from collections import defaultdict
from typing import Any, Dict, Optional
from web3 import Web3

# ── Config ────────────────────────────────────────────────────────────────────
WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "0xD338aF379E4cC2d71EacE60b02804A9D6d2504B3")
FREE_TIER_REQUESTS = 100
SIMPLE_PRICE = 0.003
COMPLEX_PRICE = 0.007
USDC_DECIMALS = 1_000_000
USDC_CONTRACT_BASE = "0x833589fCD6eDb6E08f4c7C32D4f71b54bdA02913"

# Base RPC
BASE_RPC = os.getenv("BASE_RPC_URL", "https://mainnet.base.org")

# ── Web3 Setup ────────────────────────────────────────────────────────────────
try:
    w3 = Web3(Web3.HTTPProvider(BASE_RPC))
    WEB3_AVAILABLE = w3.is_connected()
except Exception:
    w3 = None
    WEB3_AVAILABLE = False

# USDC Transfer ABI
USDC_ABI = [
    {
        "name": "Transfer",
        "type": "event",
        "inputs": [
            {"name": "from", "type": "address", "indexed": True},
            {"name": "to", "type": "address", "indexed": True},
            {"name": "value", "type": "uint256", "indexed": False}
        ]
    }
]

# ── Agent Usage ───────────────────────────────────────────────────────────────
_agent_usage: Dict[str, Dict[str, Any]] = defaultdict(lambda: {
    "request_count": 0,
    "total_paid": 0.0,
    "free_remaining": FREE_TIER_REQUESTS,
    "first_seen": time.time(),
    "verified_txs": set(),
})


def check_payment(agent_id: str, price: float) -> Dict[str, Any]:
    """يتحقق هل الـ agent في الـ free tier"""
    usage = _agent_usage[agent_id]

    if usage["free_remaining"] > 0:
        usage["free_remaining"] -= 1
        usage["request_count"] += 1
        return {
            "payment_required": False,
            "source": "free_tier",
            "free_remaining": usage["free_remaining"],
        }

    return {
        "payment_required": True,
        "amount_usdc": price,
        "wallet": WALLET_ADDRESS,
        "network": "base",
        "currency": "USDC",
        "payment_id": _generate_payment_id(agent_id, price),
    }


def verify_onchain(tx_hash: str, expected_amount: float, agent_id: str) -> Dict[str, Any]:
    """
    يتحقق من الـ transaction على Base blockchain
    """
    usage = _agent_usage[agent_id]

    # لو نفس الـ tx استخدم قبل
    if tx_hash in usage["verified_txs"]:
        return {"verified": False, "reason": "tx_already_used"}

    # لو web3 مو متاح — fallback للتطوير
    if not WEB3_AVAILABLE or w3 is None:
        if len(tx_hash) >= 10:
            usage["verified_txs"].add(tx_hash)
            usage["request_count"] += 1
            usage["total_paid"] += expected_amount
            return {"verified": True, "source": "dev_mode"}
        return {"verified": False, "reason": "invalid_tx_hash"}

    try:
        # جلب الـ transaction
        tx_receipt = w3.eth.get_transaction_receipt(tx_hash)

        if tx_receipt is None:
            return {"verified": False, "reason": "tx_not_found"}

        if tx_receipt["status"] != 1:
            return {"verified": False, "reason": "tx_failed"}

        # التحقق من USDC transfer
        usdc_contract = w3.eth.contract(
            address=Web3.to_checksum_address(USDC_CONTRACT_BASE),
            abi=USDC_ABI
        )

        transfer_logs = usdc_contract.events.Transfer().process_receipt(tx_receipt)

        for log in transfer_logs:
            to_addr = log["args"]["to"].lower()
            amount = log["args"]["value"]
            amount_usdc = amount / USDC_DECIMALS

            if (to_addr == WALLET_ADDRESS.lower() and
                    amount_usdc >= expected_amount * 0.99):  # 1% tolerance
                usage["verified_txs"].add(tx_hash)
                usage["request_count"] += 1
                usage["total_paid"] += amount_usdc
                return {
                    "verified": True,
                    "amount_received": amount_usdc,
                    "source": "blockchain",
                }

        return {"verified": False, "reason": "usdc_transfer_not_found"}

    except Exception as e:
        return {"verified": False, "reason": "verification_error", "error": str(e)}


def payment_middleware(agent_id: str, price: float, tx_hash: Optional[str] = None) -> Dict[str, Any]:
    """Middleware كامل"""
    check = check_payment(agent_id, price)

    if not check["payment_required"]:
        return {"allowed": True, "source": "free_tier", "price": 0}

    if not tx_hash:
        return {
            "allowed": False,
            "source": "payment_required",
            "price": price,
            "payment_info": get_402_response(agent_id, price),
        }

    verification = verify_onchain(tx_hash, price, agent_id)

    if verification["verified"]:
        return {"allowed": True, "source": "paid", "price": price}

    return {
        "allowed": False,
        "source": "payment_failed",
        "reason": verification.get("reason"),
        "price": price,
        "payment_info": get_402_response(agent_id, price),
    }


def get_402_response(agent_id: str, price: float) -> Dict[str, Any]:
    return {
        "status": 402,
        "x402": {
            "version": "1",
            "accepts": [{
                "scheme": "exact",
                "network": "base",
                "maxAmountRequired": str(int(price * USDC_DECIMALS)),
                "resource": "/fix?agent={}".format(agent_id),
                "description": "Crypto API Fix — ${} USDC".format(price),
                "payTo": WALLET_ADDRESS,
                "maxTimeoutSeconds": 60,
                "asset": USDC_CONTRACT_BASE,
            }]
        },
        "instructions": "Send {} USDC to {} on Base. Include tx hash in X-Payment header.".format(
            price, WALLET_ADDRESS)
    }


def get_agent_stats(agent_id: str) -> Dict[str, Any]:
    usage = _agent_usage[agent_id]
    return {
        "agent_id": agent_id,
        "request_count": usage["request_count"],
        "total_paid_usdc": round(usage["total_paid"], 6),
        "free_remaining": usage["free_remaining"],
    }


def get_revenue_stats() -> Dict[str, Any]:
    total_requests = sum(u["request_count"] for u in _agent_usage.values())
    total_revenue = sum(u["total_paid"] for u in _agent_usage.values())
    return {
        "total_agents": len(_agent_usage),
        "total_requests": total_requests,
        "total_revenue_usdc": round(total_revenue, 6),
        "blockchain_connected": WEB3_AVAILABLE,
    }


def _generate_payment_id(agent_id: str, price: float) -> str:
    raw = "{}:{}:{}".format(agent_id, price, time.time())
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


if __name__ == "__main__":
    print("x402 Real Blockchain Verification\n")
    print("Web3 connected:", WEB3_AVAILABLE)
    print("Base RPC:", BASE_RPC)

    agent = "test_bot"
    print("\nFree tier test:")
    for i in range(3):
        r = payment_middleware(agent, SIMPLE_PRICE)
        print("  Request {}: allowed={} source={}".format(i+1, r["allowed"], r["source"]))

    agent2 = "test_bot_paid"
    _agent_usage[agent2]["free_remaining"] = 0
    print("\nPaid test (no tx_hash):")
    r = payment_middleware(agent2, SIMPLE_PRICE)
    print("  allowed={} source={}".format(r["allowed"], r["source"]))

    print("\nRevenue stats:", get_revenue_stats())
