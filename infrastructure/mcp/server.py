"""
MCP Server - SSE Support for Smithery + Chat Protocol for Agentverse
"""

import os
import sys
import time
import json
import threading
import hashlib
import asyncio
import logging
from typing import Any, Dict

ROOT = os.path.join(os.path.dirname(__file__), "..", "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "training"))

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
import uvicorn

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

WALLET_ADDRESS = os.getenv("WALLET_ADDRESS", "0xD338aF379E4cC2d71EacE60b02804A9D6d2504B3")
FREE_TIER_LIMIT = 100
_agent_usage: Dict[str, int] = {}
_usage_lock = threading.Lock()

HANDLERS: Dict[str, Any] = {
    "stale_data": h_stale, "rate_limit": h_rate,
    "endpoint_down": h_fallback, "unexpected_error": h_error,
    "price_mismatch": h_price, "json_broken": h_json,
    "auth_error": h_auth, "financial_risk": h_risk,
    "websocket_dead": h_ws, "key_permission": h_key,
}

MCP_TOOLS = [
    {
        "name": "fix_stale_data",
        "x-smithery-displayName": "Fix Stale Data",
        "annotations": {"audience": ["assistant"], "priority": 0.8},
        "description": "Detects and fixes stale/outdated API responses from crypto exchanges. Fetches fresh data from backup sources. Use when price data is older than 5 seconds. Cost: $0.003/request.",
        "inputSchema": {"type": "object", "properties": {
            "status": {"type": "integer", "description": "HTTP status code from the exchange API response (e.g. 200, 429, 503)"},
            "data": {"type": "object", "description": "Raw API response data containing price, timestamp, and other fields"}
        }, "required": ["status"]}
    },
    {
        "name": "fix_rate_limit",
        "x-smithery-displayName": "Fix Rate Limit",
        "annotations": {"audience": ["assistant"], "priority": 0.9},
        "description": "Handles 429 and 503 rate limit errors. Applies smart backoff and proxy rotation. Use when exchange returns Too Many Requests. Cost: $0.003/request.",
        "inputSchema": {"type": "object", "properties": {
            "status": {"type": "integer", "description": "HTTP status code (429 or 503 for rate limits)"},
            "data": {"type": "object", "description": "Response data including retry-after headers if available"}
        }, "required": ["status"]}
    },
    {
        "name": "fix_endpoint_down",
        "x-smithery-displayName": "Fix Endpoint Down",
        "annotations": {"audience": ["assistant"], "priority": 0.9},
        "description": "Auto-failover when exchange API is down (502/503/504). Routes to backup mirrors for Binance, Coinbase, Kraken, Bybit, OKX. Cost: $0.003/request.",
        "inputSchema": {"type": "object", "properties": {
            "status": {"type": "integer", "description": "HTTP status code (502, 503, or 504 for endpoint failures)"},
            "data": {"type": "object", "description": "Response data from the failed endpoint"}
        }, "required": ["status"]}
    },
    {
        "name": "fix_unexpected_error",
        "x-smithery-displayName": "Fix Unexpected Error",
        "annotations": {"audience": ["assistant"], "priority": 0.7},
        "description": "Fixes unexpected 500 errors, null values, and wrong data types in API responses. Cost: $0.003/request.",
        "inputSchema": {"type": "object", "properties": {
            "status": {"type": "integer", "description": "HTTP status code (500 for server errors)"},
            "data": {"type": "object", "description": "Response data that may contain null values or wrong types"}
        }, "required": ["status"]}
    },
    {
        "name": "fix_price_mismatch",
        "x-smithery-displayName": "Fix Price Mismatch",
        "annotations": {"audience": ["assistant"], "priority": 0.8},
        "description": "Cross-exchange price validation. Detects outliers over 3% deviation and computes median price. Use when prices differ significantly between exchanges. Cost: $0.007/request.",
        "inputSchema": {"type": "object", "properties": {
            "status": {"type": "integer", "description": "HTTP status code from exchange API"},
            "data": {"type": "object", "description": "Response data containing prices from multiple exchanges"}
        }, "required": ["status"]}
    },
    {
        "name": "fix_json_broken",
        "x-smithery-displayName": "Fix Broken JSON",
        "annotations": {"audience": ["assistant"], "priority": 0.8},
        "description": "Repairs malformed JSON, schema changes, and missing required fields. Auto-remaps Binance, Coinbase, Kraken schemas. Cost: $0.007/request.",
        "inputSchema": {"type": "object", "properties": {
            "status": {"type": "integer", "description": "HTTP status code from exchange API"},
            "data": {"type": "object", "description": "Partially parsed response data"},
            "raw": {"type": "string", "description": "Raw unparsed response string if JSON parsing failed"}
        }, "required": ["status"]}
    },
    {
        "name": "fix_auth_error",
        "x-smithery-displayName": "Fix Auth Error",
        "annotations": {"audience": ["assistant"], "priority": 0.9},
        "description": "Fixes 401/403 authentication errors. Rotates API keys, recalculates HMAC signatures, syncs timestamps. Cost: $0.007/request.",
        "inputSchema": {"type": "object", "properties": {
            "status": {"type": "integer", "description": "HTTP status code (401 for unauthorized, 403 for forbidden)"},
            "data": {"type": "object", "description": "Exchange error response with message about auth failure"}
        }, "required": ["status"]}
    },
    {
        "name": "fix_financial_risk",
        "x-smithery-displayName": "Fix Financial Risk",
        "annotations": {"audience": ["assistant"], "priority": 1.0},
        "description": "Real-time circuit breaker for price spikes over 3%, low liquidity, or API latency over 500ms. Pauses trading to prevent losses. Cost: $0.007/request.",
        "inputSchema": {"type": "object", "properties": {
            "status": {"type": "integer", "description": "HTTP status code from exchange API"},
            "data": {"type": "object", "description": "Market data including change_pct, order_book_depth, and latency_ms"}
        }, "required": ["status"]}
    },
    {
        "name": "fix_websocket_dead",
        "x-smithery-displayName": "Fix Dead WebSocket",
        "annotations": {"audience": ["assistant"], "priority": 0.8},
        "description": "Detects silent WebSocket disconnections and reconnects automatically. Use when no data received for over 30 seconds. Cost: $0.003/request.",
        "inputSchema": {"type": "object", "properties": {
            "status": {"type": "integer", "description": "HTTP status code or 0 for WebSocket connections"},
            "data": {"type": "object", "description": "Connection data including connected status and last_message_ago_seconds"}
        }, "required": ["status"]}
    },
    {
        "name": "fix_key_permission",
        "x-smithery-displayName": "Fix Key Permission",
        "annotations": {"audience": ["assistant"], "priority": 0.9},
        "description": "Validates API key permissions. Alerts on dangerous withdrawal permissions and switches to safe trading mode. Cost: $0.003/request.",
        "inputSchema": {"type": "object", "properties": {
            "status": {"type": "integer", "description": "HTTP status code (403 for permission errors)"},
            "data": {"type": "object", "description": "Exchange error response with permission details"}
        }, "required": ["status"]}
    },
    {
        "name": "auto_fix",
        "x-smithery-displayName": "Auto Fix",
        "annotations": {"audience": ["assistant"], "priority": 0.7},
        "description": "Auto-detects and fixes any crypto exchange API error. Use this when you are unsure of the error type. Handles all 10 error categories automatically.",
        "inputSchema": {"type": "object", "properties": {
            "status": {"type": "integer", "description": "HTTP status code from the exchange API response"},
            "data": {"type": "object", "description": "Raw API response data"},
            "headers": {"type": "object", "description": "Response headers from the exchange API"},
            "raw": {"type": "string", "description": "Raw unparsed response string if available"}
        }, "required": ["status"]}
    },
]

app = FastAPI(title="Crypto API Fixer", version="1.0.0")

from fastapi.middleware.cors import CORSMiddleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
    expose_headers=["*"],
    max_age=86400,
)


async def _process_fix(body: Dict[str, Any], agent_id: str = "unknown") -> Dict[str, Any]:
    start = time.time()
    try:
        detection = await asyncio.to_thread(detect, body)
        error_type = detection.get("error_type", "none")
        if error_type == "none":
            return {"status": "ok", "message": "no error detected", "latency_ms": round((time.time()-start)*1000, 2)}
        pattern = await asyncio.to_thread(match, detection)
        price = get_pricing(pattern)
        if pattern and not should_use_agents_loop(pattern):
            return {"status": "fixed", "source": "solution_db", "error_type": error_type,
                    "solution": pattern.get("solution", {}), "trading_safe": True,
                    "price_usd": price, "latency_ms": round((time.time()-start)*1000, 2)}
        handler = HANDLERS.get(error_type)
        if handler:
            result = await asyncio.to_thread(handler, detection, body)
            source = "handler"
        else:
            result = await asyncio.to_thread(run_agents_loop, detection, body)
            source = result.get("source", "agents_loop")
        latency = round((time.time()-start)*1000, 2)
        return {"status": "fixed" if result.get("fixed") else "escalated", "source": source,
                "error_type": error_type, "solution": result, "price_usd": price, "latency_ms": latency}
    except Exception as e:
        return {"status": "error", "message": str(e), "latency_ms": round((time.time()-start)*1000, 2)}


@app.get("/health")
async def health():
    return {"status": "ok", "version": "1.0.0", "tools": len(MCP_TOOLS)}


@app.get("/.well-known/mcp/server-card.json")
async def mcp_server_card():
    return {
        "schema_version": "v1",
        "name": "crypto-api-fixer",
        "displayName": "Crypto API Fixer",
        "version": "1.0.0",
        "description": "Auto-repair middleware for crypto trading bots. Automatically detects and fixes 10 types of exchange API errors in under 2ms.",
        "transport": {
            "type": "streamable-http",
            "url": "https://crypto-api-fixer.fly.dev/mcp"
        },
        "capabilities": {"tools": True},
        "tools": MCP_TOOLS
    }


@app.get("/.well-known/agent-card.json")
async def agent_card():
    return {"name": "Crypto API Fixer", "version": "1.0.0",
            "capabilities": ["api_repair", "price_validation", "risk_guard", "auth_fix"],
            "endpoint": "/fix", "payment": {"protocol": "x402", "currency": "USDC", "network": "base"}}


@app.post("/fix")
async def fix_endpoint(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "invalid JSON"}, status_code=400)
    agent_id = hashlib.sha256(str(request.headers.get("User-Agent", "unknown")).encode()).hexdigest()[:12]
    result = await _process_fix(body, agent_id)
    return result


# ── Chat Protocol for Agentverse/ASI:One ─────────────────────────────────────

@app.post("/chat")
async def chat_endpoint(request: Request):
    """Chat Protocol for Agentverse/ASI:One discovery"""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"status": "error", "message": "invalid JSON"}, status_code=400)

    message = ""
    if isinstance(body.get("content"), list):
        for item in body["content"]:
            if item.get("type") == "text":
                message = item.get("text", "").lower()
                break
    elif isinstance(body.get("content"), str):
        message = body["content"].lower()

    if any(w in message for w in ["rate limit", "429", "503", "too many"]):
        reply = "Rate limit detected. I apply smart backoff + retry with exponential delay. Send the full API response to POST /fix for automatic repair in under 2ms."
    elif any(w in message for w in ["stale", "old data", "timestamp", "outdated"]):
        reply = "Stale data detected. I fetch fresh data from backup sources automatically. Send the API response to POST /fix for repair."
    elif any(w in message for w in ["auth", "401", "403", "api key", "signature", "unauthorized"]):
        reply = "Auth error detected. I handle key rotation and signature repair. Send the API response to POST /fix for automatic repair."
    elif any(w in message for w in ["down", "502", "504", "endpoint", "gateway", "timeout"]):
        reply = "Endpoint down. I auto-failover to backup mirrors for Binance, Coinbase, Kraken, Bybit, OKX. Send the response to POST /fix."
    elif any(w in message for w in ["price", "mismatch", "spread", "deviation"]):
        reply = "Price mismatch detected. I compute cross-exchange median to get the correct price. Send the response to POST /fix."
    elif any(w in message for w in ["json", "broken", "parse", "malformed", "schema"]):
        reply = "Broken JSON detected. I repair schemas and remap Binance/Coinbase/Kraken formats. Send the response to POST /fix."
    elif any(w in message for w in ["websocket", "ws", "disconnect", "reconnect"]):
        reply = "WebSocket dead. I silently reconnect with state recovery. Send the connection data to POST /fix."
    elif any(w in message for w in ["risk", "spike", "liquidity", "circuit"]):
        reply = "Financial risk detected. I activate the circuit breaker for price spikes over 3% or low liquidity. Send data to POST /fix."
    elif any(w in message for w in ["permission", "withdrawal", "read only"]):
        reply = "Key permission issue. I switch to safe degraded mode and alert on dangerous permissions. Send data to POST /fix."
    elif any(w in message for w in ["500", "internal server", "unexpected"]):
        reply = "Unexpected 500 error. I clean the response and apply smart retry logic. Send to POST /fix."
    else:
        reply = (
            "I am Crypto API Fixer — auto-repair middleware for trading bots. "
            "I fix 10 API error types in under 2ms: rate limits (429/503), stale data, "
            "auth errors (401/403), endpoint down (502/504), price mismatch, broken JSON, "
            "WebSocket disconnects, key permission issues, financial risk, and unexpected 500 errors. "
            "Works with Binance, Coinbase, Kraken, Bybit, OKX. "
            "Send your API error to POST /fix for automatic repair. "
            "First 100 requests free. Paid via x402 on Base (USDC)."
        )

    return JSONResponse({
        "content": [{"type": "text", "text": reply}],
        "role": "assistant"
    })


# ── MCP SSE Protocol ──────────────────────────────────────────────────────────

@app.api_route("/mcp", methods=["GET", "POST", "OPTIONS"])
async def mcp_endpoint(request: Request):
    """Combined SSE + JSON-RPC endpoint for Smithery"""

    if request.method == "OPTIONS":
        from fastapi.responses import Response
        return Response(
            status_code=204,
            headers={
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "*",
                "Access-Control-Max-Age": "86400",
            }
        )

    if request.method == "GET":
        async def sse_stream():
            yield "event: message\n"
            yield "data: {\"status\":\"ok\"}\n\n"
            while True:
                if await request.is_disconnected():
                    break
                await asyncio.sleep(15)
                yield "event: keepalive\n"
                yield "data: {\"status\":\"ok\"}\n\n"

        return StreamingResponse(
            sse_stream(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
                "X-Accel-Buffering": "no",
            }
        )

    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"jsonrpc": "2.0", "error": {"code": -32700, "message": "Parse error"}})

    method = body.get("method", "")
    req_id = body.get("id")

    if method == "initialize":
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {
            "protocolVersion": "2025-11-25",
            "serverInfo": {"name": "crypto-api-fixer", "version": "1.0.0"},
            "capabilities": {"tools": {}}
        }})

    elif method == "tools/list":
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {"tools": MCP_TOOLS}})

    elif method == "tools/call":
        tool_name = body.get("params", {}).get("name", "")
        args = body.get("params", {}).get("arguments", {})
        error_map = {
            "fix_stale_data": "stale_data", "fix_rate_limit": "rate_limit",
            "fix_endpoint_down": "endpoint_down", "fix_unexpected_error": "unexpected_error",
            "fix_price_mismatch": "price_mismatch", "fix_json_broken": "json_broken",
            "fix_auth_error": "auth_error", "fix_financial_risk": "financial_risk",
            "fix_websocket_dead": "websocket_dead", "fix_key_permission": "key_permission",
        }
        if tool_name in error_map:
            args["error_type"] = error_map[tool_name]
        result = await _process_fix(args)
        return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {
            "content": [{"type": "text", "text": json.dumps(result)}]
        }})

    return JSONResponse({"jsonrpc": "2.0", "id": req_id, "result": {}})


if __name__ == "__main__":
    uvicorn.run("server:app", host="0.0.0.0", port=8080, workers=1, reload=False)
