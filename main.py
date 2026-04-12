"""
Main Entry Point
Runs the full tool — connects everything
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'training'))

import signal
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

# Maximum time (seconds) for the agents loop before timeout
AGENTS_LOOP_TIMEOUT = 30


class AgentsLoopTimeout(Exception):
    pass


def _timeout_handler(signum, frame):
    raise AgentsLoopTimeout("Agents loop exceeded timeout")


def _validate_input(api_response: Any) -> bool:
    """Validate that api_response is a dict with minimum required fields."""
    if not isinstance(api_response, dict):
        return False
    return True


def fix(api_response: Dict[str, Any], agent_id: str = "unknown") -> Dict[str, Any]:
    """
    Main fix function.
    Receives any API response and returns the solution.
    """
    start = time.time()

    try:
        # Input validation
        if not _validate_input(api_response):
            return {
                "fixed": False,
                "status": "error",
                "message": "Invalid input: api_response must be a dict",
                "latency_ms": round((time.time() - start) * 1000, 2),
            }

        # 1. Detect the problem
        detection = detect(api_response)
        error_type = detection.get("error_type", "none")

        if error_type == "none":
            return {
                "fixed": True,
                "status": "ok",
                "message": "no error detected",
                "latency_ms": round((time.time() - start) * 1000, 2),
            }

        # 2. Determine pricing
        pattern = match(detection)
        price = get_pricing(pattern)

        # 3. Check payment
        payment = payment_middleware(agent_id, price)
        if not payment.get("allowed", False):
            return {
                "fixed": False,
                "status": "payment_required",
                "payment_info": payment.get("payment_info", {}),
                "latency_ms": round((time.time() - start) * 1000, 2),
            }

        # 4. Solution DB first (cached fix)
        if pattern and not should_use_agents_loop(pattern):
            latency = round((time.time() - start) * 1000, 2)
            log_fix(error_type, str(pattern["solution"].get("action")), "solution_db", price, latency, agent_id)
            record_fix(agent_id, error_type, str(pattern["solution"].get("action")), "solution_db", price, latency, True)
            return {
                "fixed": True,
                "status": "fixed",
                "source": "solution_db",
                "error_type": error_type,
                "solution": pattern["solution"],
                "price_usd": price,
                "latency_ms": latency,
            }

        # 5. Handler or agents loop
        handler = HANDLERS.get(error_type)
        if handler:
            result = handler(detection, api_response)
            source = "handler"
        else:
            # Run agents loop with timeout protection
            try:
                if hasattr(signal, 'SIGALRM'):
                    old_handler = signal.signal(signal.SIGALRM, _timeout_handler)
                    signal.alarm(AGENTS_LOOP_TIMEOUT)

                result = run_agents_loop(detection, api_response)
                source = result.get("source", "agents_loop")

                if hasattr(signal, 'SIGALRM'):
                    signal.alarm(0)
                    signal.signal(signal.SIGALRM, old_handler)
            except AgentsLoopTimeout:
                log_error("Agents loop timed out after {}s for error_type={}".format(
                    AGENTS_LOOP_TIMEOUT, error_type))
                return {
                    "fixed": False,
                    "status": "timeout",
                    "error_type": error_type,
                    "message": "Agents loop timed out after {}s".format(AGENTS_LOOP_TIMEOUT),
                    "latency_ms": round((time.time() - start) * 1000, 2),
                }

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
    """Start the MCP HTTP server"""
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
        print("Training mode\n")
        run_training(count=args.samples, reset_db=True, verbose=True)

    elif args.mode == "server":
        print("Server mode\n")
        run_training(count=500, reset_db=False, verbose=False)
        reset_circuit_breaker()
        run_server(port=args.port)

    else:
        # test mode
        from training.broken_api_generator import generate_one, ERROR_TYPES

        run_training(count=500, reset_db=True, verbose=False)
        reset_circuit_breaker()

        print("Test mode\n")
        print("=" * 65)

        fixed = 0
        for error_type in ERROR_TYPES:
            error = generate_one(error_type)
            result = fix(error, agent_id="test_bot")
            status = "OK" if result.get("fixed") else "FAIL"
            print("{} {:<25} status={:<10} source={:<15} {}ms".format(
                status, error_type,
                result.get("status", "?"),
                result.get("source", "?"),
                result.get("latency_ms", 0)))
            if result.get("fixed"):
                fixed += 1

        print("\n" + "=" * 65)
        print("Fixed: {}/{}".format(fixed, len(ERROR_TYPES)))
        print("Revenue stats:", get_revenue_stats())
