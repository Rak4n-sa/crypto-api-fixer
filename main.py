"""
Main Entry Point
يشغّل الأداة كاملة — يربط كل شيء
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'training'))

import time
from typing import Any, Dict

from core.detector import detect
from training.pattern_matcher import match, should_use_agents_loop, get_pricing
from training.trainer import run_training
from utils.logger import logger, log_fix, log_error
from infrastructure.payments.x402 import payment_middleware, get_revenue_stats
from training.archive_db import record_fix, get_agent_weekly_report

from handlers.stale_data import handle as h_stale
from handlers.rate_limit import handle as h_rate
from handlers.fallback import handle as h_fallback
from handlers.error_handler import handle as h_error
from handlers.price_validator import handle as h_price
from handlers.json_repair import handle as h_json
from handlers.auth_fixer import handle as h_auth
from handlers.risk_guard import handle as h_risk, reset_circuit_breaker
from handlers.websocket_monitor import handle as h_ws
from handlers.key_validator import handle as h_key
from agents.loop import run as run_agents_loop

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


def fix(api_response: Dict[str, Any], agent_id: str = "unknown") -> Dict[str, Any]:
    """
    الدالة الرئيسية
    تستقبل أي API response وترجع الحل
    """
    start = time.time()

    try:
        # ١. اكتشاف المشكلة
        detection = detect(api_response)
        error_type = detection.get("error_type", "none")

        if error_type == "none":
            return {
                "fixed": True,
                "status": "ok",
                "message": "no error detected",
                "latency_ms": round((time.time() - start) * 1000, 2),
            }

        # ٢. تحديد السعر
        pattern = match(detection)
        price = get_pricing(pattern)

        # ٣. فحص الدفع
        payment = payment_middleware(agent_id, price)
        if not payment.get("allowed", False):
            return {
                "fixed": False,
                "status": "payment_required",
                "payment_info": payment.get("payment_info", {}),
                "latency_ms": round((time.time() - start) * 1000, 2),
            }

        # ٤. solution DB أولاً
        if pattern and not should_use_agents_loop(pattern):
            latency = round((time.time() - start) * 1000, 2)
            log_fix(error_type, str(pattern["solution"].get("action")), "solution_db", price, latency, agent_id)
            record_fix(agent_id, error_type, str(pattern["solution"].get("action")), "solution_db", price, latency)
            return {
                "fixed": True,
                "status": "fixed",
                "source": "solution_db",
                "error_type": error_type,
                "solution": pattern["solution"],
                "price_usd": price,
                "latency_ms": latency,
            }

        # ٥. handler أو agents loop
        handler = HANDLERS.get(error_type)
        if handler:
            result = handler(detection, api_response)
            source = "handler"
        else:
            result = run_agents_loop(detection, api_response)
            source = result.get("source", "agents_loop")

        latency = round((time.time() - start) * 1000, 2)
        log_fix(error_type, str(result.get("action")), source, price, latency, agent_id)
        record_fix(agent_id, error_type, str(result.get("action")), source, price, latency, result.get("fixed", False))

        return {
            "fixed": result.get("fixed", False),
            "status": "fixed" if result.get("fixed") else "escalated",
            "source": source,
            "error_type": error_type,
            "severity": detection.get("severity"),
            "financial_risk": detection.get("financial_risk"),
            "solution": result,
            "trading_safe": not detection.get("financial_risk", False),
            "price_usd": price,
            "latency_ms": latency,
        }

    except Exception as e:
        log_error("fix() crashed: {}".format(str(e)))
        return {
            "fixed": False,
            "status": "error",
            "message": str(e),
            "latency_ms": round((time.time() - start) * 1000, 2),
        }


def run_server(host: str = "0.0.0.0", port: int = 8080) -> None:
    """يشغّل الـ MCP HTTP server"""
    from http.server import HTTPServer
    from infrastructure.mcp.server import MCPHandler

    logger.info("Starting Crypto API Fixer on {}:{}".format(host, port))
    server = HTTPServer((host, port), MCPHandler)
    logger.info("Server ready — http://{}:{}".format(host, port))
    server.serve_forever()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Crypto API Fixer")
    parser.add_argument("--mode", choices=["server", "train", "test"], default="test")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--samples", type=int, default=1000)
    args = parser.parse_args()

    if args.mode == "train":
        print("🎓 Training mode\n")
        run_training(count=args.samples, reset_db=True, verbose=True)

    elif args.mode == "server":
        print("🚀 Server mode\n")
        run_training(count=500, reset_db=False, verbose=False)
        reset_circuit_breaker()
        run_server(port=args.port)

    else:
        # test mode
        from training.broken_api_generator import generate_one, ERROR_TYPES

        run_training(count=500, reset_db=True, verbose=False)
        reset_circuit_breaker()

        print("🧪 Test mode\n")
        print("=" * 65)

        fixed = 0
        for error_type in ERROR_TYPES:
            error = generate_one(error_type)
            result = fix(error, agent_id="test_bot")
            icon = "✅" if result.get("fixed") else "❌"
            print("{} {:<25} status={:<10} source={:<15} {}ms".format(
                icon, error_type,
                result.get("status", "?"),
                result.get("source", "?"),
                result.get("latency_ms", 0)))
            if result.get("fixed"):
                fixed += 1

        print("\n" + "=" * 65)
        print("📊 Fixed: {}/{}".format(fixed, len(ERROR_TYPES)))
        print("💰 Revenue stats:", get_revenue_stats())
