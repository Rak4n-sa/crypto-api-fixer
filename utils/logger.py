"""
Logger
نظام logging موحد للمشروع كله
"""

import logging
from typing import Any

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger("crypto_api_fixer")


def log_fix(
    error_type: str,
    action: Any,
    source: Any,
    price: float,
    latency: float,
    agent_id: str = "unknown"
) -> None:
    try:
        action_str = str(action) if action is not None else "unknown"
        source_str = str(source) if source is not None else "unknown"
        logger.info("FIX | agent={} | {:<20} action={:<30} source={:<12} ${:.4f} {:.2f}ms".format(
            agent_id, error_type, action_str, source_str, price, latency))
    except Exception as e:
        logger.error("LOG_FIX_ERROR | {}".format(str(e)))


def log_error(message: str) -> None:
    try:
        logger.error("ERROR | {}".format(message))
    except Exception:
        pass


def log_payment(agent_id: str, amount: float, source: str) -> None:
    try:
        logger.info("PAYMENT | agent={} amount=${:.4f} source={}".format(
            agent_id, amount, source))
    except Exception:
        pass
