import json
import logging
from typing import Any, Dict

logger = logging.getLogger(__name__)


def _log_event(prefix: str, payload: Dict[str, Any]) -> None:
    """Emit ingestion telemetry as a single log line (no logger extra=)."""
    safe_payload = {k: v for k, v in payload.items() if v is not None}
    logger.info("%s %s", prefix, json.dumps(safe_payload, default=str))


def log_ingestion_route_decision(payload: Dict[str, Any]) -> None:
    payload = {"event": "ingestion.route_decision", **payload}
    _log_event("ingestion.route_decision", payload)


def log_ingestion_completed(payload: Dict[str, Any]) -> None:
    payload = {"event": "ingestion.completed", **payload}
    _log_event("ingestion.completed", payload)


def log_ingestion_failed(payload: Dict[str, Any]) -> None:
    payload = {"event": "ingestion.failed", **payload}
    _log_event("ingestion.failed", payload)
