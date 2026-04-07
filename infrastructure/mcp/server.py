"""
MCP Server - Production Ready (FastAPI + Uvicorn)
يستحمل آلاف الـ requests بالثانية
"""

import os
import sys
import time
import threading
import hashlib
import logging
from typing import Any, Dict, Optional

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "training"))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import uvicorn
import asyncio

from core.detector import detect
from training.pattern_matcher import match, should_use_agents_loop, get_pricing
from agents.loop import run as run_agents_loop
from utils.logger import logger, log_fix

from handlers.stale_data import handle as h_stale
from handlers.rate_limit import handle as h_rate
from handlers.fallback import handle as h_fallback
from handlers.error_handler import handle as h_error
from handlers.price_validator import handle as h_price
from handlers.json_repair import handle as h_json
from handlers.auth_fixer import handle as h_auth
from handlers.risk_guard import handle as h_risk
from handlers.websocket_monitor import handle as h_ws
from handlers.key_validator import handle as h_key

# ── Config ────────────────────────────────────────────────────────────────────

WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "0xD338aF379E4cC2d71EacE60b02804A9D6d2504B3")
FREE_TIER_LIMIT = 100

_agent_usage: Dict[str, int] = {}
_usage_lock = threading.Lock()

HANDLERS: Dict[str, Any] = {
    "stale_data":       h_stale,
    "rate_limit":       h_rate,
    "endpoint_down":    h_fallback,
    "unexpected_error": h_error,
    "price_mismatch":   h_price,
    "json_broken":      h_json,
    "auth_error":       h_auth,
    "financial_risk":   h_risk,
    "websocket_dead":   h_ws,
    "key_permission":   h_key,
}

MCP_TOOLS = [
    {
        "name": "fix_stale_data",
        "category": "data_freshness",
        "description": "Detects and fixes stale API responses. Fetches fresh data from backup. $0.003/request.",
        "inputSchema": {"type": "object", "properties": {"status": {"type": "integer"}, "data": {"type": "object"}}, "required": ["status"]},
    },
    {
        "name": "fix_rate_limit",
        "category": "throttling",
        "description": "Handles 429/503 rate limit errors. Backoff + proxy rotation. $0.003/request.",
        "inputSchema": {"type": "object", "properties": {"status": {"type": "integer"}, "headers": {"type": "object"}}, "required": ["status"]},
    },
    {
        "name": "fix_endpoint_down",
        "category": "availability",
        "description": "Auto-failover to backup endpoints (502/503/504). $0.003/request.",
        "inputSchema": {"type": "object", "properties": {"status": {"type": "integer"}}, "required": ["status"]},
    },
    {
        "name": "fix_unexpected_error",
        "category": "error_recovery",
        "description": "Fixes 500 errors, null values, wrong types. $0.003/request.",
        "inputSchema": {"type": "object", "properties": {"status": {"type": "integer"}, "data": {"type": "object"}}, "required": ["status"]},
    },
    {
        "name": "fix_price_mismatch",
        "category": "price_validation",
        "description": "Cross-exchange price validation. Removes outliers. $0.007/request.",
        "inputSchema": {"type": "object", "properties": {"status": {"type": "integer"}, "data": {"type": "object"}}, "required": ["status"]},
    },
    {
        "name": "fix_json_broken",
        "category": "data_repair",
        "description": "Repairs malformed JSON, schema changes, missing fields. $0.007/request.",
        "inputSchema": {"type": "object", "properties": {"status": {"type": "integer"}, "data": {"type": "object"}, "raw": {"type": "string"}}, "required": ["status"]},
    },
    {
        "name": "fix_auth_error",
        "category": "authentication",
        "description": "Fixes 401/403 errors. Key rotation + signature fix. $0.007/request.",
        "inputSchema": {"type": "object", "properties": {"status": {"type": "integer"}, "data": {"type": "object"}}, "required": ["status"]},
    },
    {
        "name": "fix_financial_risk",
        "category": "risk_management",
        "description": "Circuit breaker for price spikes + low liquidity. $0.007/request.",
        "inputSchema": {"type": "object", "properties": {"status": {"type": "integer"}, "data": {"type": "object"}}, "required": ["status"]},
    },
    {
        "name": "fix_websocket_dead",
        "category": "connectivity",
        "description": "Reconnects dead WebSocket streams silently. $0.003/request.",
        "inputSchema": {"type": "object", "properties": {"status": {"type": "integer"}, "data": {"type": "object"}}, "required": ["status"]},
    },
    {
        "name": "fix_key_permission",
        "category": "security",
        "description": "Validates API key permissions. Alerts on withdrawal risk. $0.003/request.",
        "inputSchema": {"type": "object", "properties": {"status": {"type": "integer"}, "data": {"type": "object"}}, "required": ["status"]},
    },
]

# ── FastAPI App ───────────────────────────────────────────────────────────────

app = FastAPI(title="Crypto API Fixer", version="1.0.0")


def _get_agent_id(request: Request) -> str:
    raw = request.headers.get("X-Agent-ID") or request.headers.get("User-Agent", "unknown")
    return hashlib.sha256(str(raw).encode()).hexdigest()[:12]


def _check_payment(agent_id: str, price: float, request: Request) -> Dict[str, Any]:
    """
    يتحقق من الدفع:
    ١. free tier أول 100 request
    ٢. بعدها يتحقق من X-Payment header
    """
    with _usage_lock:
        usage = _agent_usage.get(agent_id, 0)
        if usage < FREE_TIER_LIMIT:
            _agent_usage[agent_id] = usage + 1
            return {
                "allowed": True,
                "source": "free_tier",
                "remaining": FREE_TIER_LIMIT - usage - 1
            }

    # قراءة الـ payment token من الـ headers
    payment_token = (
        request.headers.get("X-Payment", "") or
        request.headers.get("Authorization", "").replace("Bearer ", "")
    )

    if payment_token and len(payment_token) >= 10:
        with _usage_lock:
            _agent_usage[agent_id] = _agent_usage.get(agent_id, 0) + 1
        logger.info("PAYMENT | agent={} amount=${}".format(agent_id, price))
        return {"allowed": True, "source": "paid"}

    return {
        "allowed": False,
        "amount_usdc": price,
        "wallet": WALLET_ADDRESS,
        "network": "base",
        "currency": "USDC",
        "instructions": "Send {} USDC to {} on Base. Include tx hash in X-Payment header.".format(
            price, WALLET_ADDRESS)
    }


def _build_agent_message(error_type: str, result: Dict[str, Any]) -> str:
    if not result.get("fixed"):
        messages = {
            "auth_error": "Auth fix failed — rotate key manually.",
            "json_broken": "JSON repair failed — use fix_json_broken with raw field.",
            "financial_risk": "Financial risk detected — trading paused.",
            "price_mismatch": "Price spread too high — wait 30s and retry.",
        }
        return messages.get(error_type, "Fix failed for {}".format(error_type))
    return "Fixed: {}".format(result.get("action", "unknown"))


# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "tools": len(MCP_TOOLS)}


@app.get("/mcp")
async def mcp_discovery():
    return {
        "protocol": "mcp",
        "version": "1.0",
        "name": "crypto-api-fixer",
        "tools": MCP_TOOLS,
        "pricing": {
            "simple_fix": "$0.003/request",
            "complex_fix": "$0.007/request",
            "free_tier": "100 requests/agent",
        },
    }


@app.get("/.well-known/agent-card.json")
async def agent_card():
    return {
        "name": "Crypto API Fixer",
        "version": "1.0.0",
        "capabilities": ["api_repair", "price_validation", "risk_guard", "auth_fix"],
        "endpoint": "/fix",
        "payment": {"protocol": "x402", "currency": "USDC", "network": "base"},
    }


@app.get("/openapi-spec.json")
async def openapi_spec():
    return {
        "openapi": "3.0.0",
        "info": {"title": "Crypto API Fixer", "version": "1.0.0"},
        "paths": {
            "/fix": {"post": {"summary": "Fix broken crypto API response"}},
            "/health": {"get": {"summary": "Health check"}},
        },
    }


@app.post("/fix")
async def fix_endpoint(request: Request):
    start = time.time()
    agent_id = _get_agent_id(request)

    # parse body
    try:
        body = await request.json()
    except Exception:
        return JSONResponse(
            {"status": "error", "message": "invalid JSON"},
            status_code=400
        )

    try:
        # detect
        detection = await asyncio.to_thread(detect, body)
        error_type = detection.get("error_type", "none")

        if error_type == "none":
            return {"status": "ok", "message": "no error detected",
                    "latency_ms": round((time.time() - start) * 1000, 2)}

        # pricing
        pattern = await asyncio.to_thread(match, detection)
        price = get_pricing(pattern)

        # x402 payment check
        payment = _check_payment(agent_id, price, request)
        if not payment.get("allowed"):
            return JSONResponse(
                {"status": "payment_required", "x402": payment,
                 "latency_ms": round((time.time() - start) * 1000, 2)},
                status_code=402
            )

        # solution DB hit
        if pattern and not should_use_agents_loop(pattern):
            latency = round((time.time() - start) * 1000, 2)
            return {
                "status": "fixed", "source": "solution_db",
                "error_type": error_type,
                "solution": pattern.get("solution", {}),
                "trading_safe": True,
                "price_usd": price,
                "latency_ms": latency
            }

        # run handler in thread pool (sync handlers)
        handler = HANDLERS.get(error_type)
        if handler:
            result = await asyncio.to_thread(handler, detection, body)
            source = "handler"
        else:
            result = await asyncio.to_thread(run_agents_loop, detection, body)
            source = result.get("source", "agents_loop")

        latency = round((time.time() - start) * 1000, 2)
        log_fix(error_type, str(result.get("action")), source, price, latency, agent_id)

        return {
            "status": "fixed" if result.get("fixed") else "escalated",
            "source": source,
            "error_type": error_type,
            "severity": detection.get("severity"),
            "financial_risk": detection.get("financial_risk"),
            "solution": result,
            "agent_message": _build_agent_message(error_type, result),
            "trading_safe": not detection.get("financial_risk", False),
            "price_usd": price,
            "latency_ms": latency,
        }

    except Exception as e:
        logger.exception("ERROR | agent={} | {}".format(agent_id, str(e)))
        return JSONResponse(
            {"status": "error", "message": str(e),
             "latency_ms": round((time.time() - start) * 1000, 2)},
            status_code=500
        )


if __name__ == "__main__":
    uvicorn.run(
        "server:app",
        host="0.0.0.0",
        port=8080,
        workers=1,  # single worker — scale via fly.io machines
        reload=False
    )
