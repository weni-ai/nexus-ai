"""Prometheus metrics HTTP exporter for Celery worker processes (Phase 0).

Celery prefork workers record metrics in forked child processes. This module
serves them from the worker parent via prometheus_client multiprocess mode on
the same path and auth scheme as the Nexus API (/api/prometheus/).
"""

from __future__ import annotations

import logging
import os
import threading
from typing import Callable, Optional

from celery.signals import worker_process_shutdown, worker_ready
from prometheus_client import CONTENT_TYPE_LATEST, CollectorRegistry, generate_latest, multiprocess
from wsgiref.simple_server import WSGIServer, make_server

logger = logging.getLogger(__name__)

PROMETHEUS_METRICS_PATHS = frozenset({"/api/prometheus/", "/api/prometheus"})
_exporter_started = False
_exporter_lock = threading.Lock()


def _is_exporter_enabled() -> bool:
    if os.environ.get("PROMETHEUS_CELERY_EXPORT_ENABLED", "true").lower() in {"0", "false", "no"}:
        return False
    return bool(os.environ.get("PROMETHEUS_MULTIPROC_DIR"))


def _authorize_request(environ: dict) -> bool:
    token = os.environ.get("PROMETHEUS_AUTH_TOKEN", "")
    if not token:
        return False
    auth_header = environ.get("HTTP_AUTHORIZATION", "")
    return auth_header == f"Bearer {token}"


def _render_metrics() -> bytes:
    registry = CollectorRegistry()
    multiprocess.MultiProcessCollector(registry)
    return generate_latest(registry)


def create_prometheus_wsgi_app() -> Callable:
    """WSGI app exposing multiprocess Celery metrics at /api/prometheus/."""

    def app(environ, start_response):
        path = environ.get("PATH_INFO", "")
        if path not in PROMETHEUS_METRICS_PATHS:
            start_response("404 Not Found", [("Content-Type", "text/plain; charset=utf-8")])
            return [b"Not Found"]

        if not _authorize_request(environ):
            start_response("403 Forbidden", [("Content-Type", "text/plain; charset=utf-8")])
            return [b"Acesso negado"]

        try:
            payload = _render_metrics()
        except Exception:
            logger.exception("Failed to render Celery Prometheus metrics")
            start_response("500 Internal Server Error", [("Content-Type", "text/plain; charset=utf-8")])
            return [b"Internal Server Error"]

        start_response("200 OK", [("Content-Type", CONTENT_TYPE_LATEST)])
        return [payload]

    return app


def start_celery_prometheus_exporter() -> None:
    """Start a background HTTP server in the Celery worker parent process."""
    global _exporter_started

    if not _is_exporter_enabled():
        logger.info("Celery Prometheus exporter disabled (PROMETHEUS_MULTIPROC_DIR unset or export disabled)")
        return

    with _exporter_lock:
        if _exporter_started:
            return

        port = int(os.environ.get("PROMETHEUS_METRICS_PORT", "9100"))
        app = create_prometheus_wsgi_app()
        server = make_server("0.0.0.0", port, app, WSGIServer)

        thread = threading.Thread(target=server.serve_forever, name="celery-prometheus-exporter", daemon=True)
        thread.start()
        _exporter_started = True

        logger.info(
            "Celery Prometheus exporter listening on 0.0.0.0:%s/api/prometheus/ (multiproc dir: %s)",
            port,
            os.environ.get("PROMETHEUS_MULTIPROC_DIR"),
        )


@worker_ready.connect
def _start_exporter_on_worker_ready(sender=None, **kwargs) -> None:
    start_celery_prometheus_exporter()


@worker_process_shutdown.connect
def _mark_worker_process_dead(pid: Optional[int] = None, **kwargs) -> None:
    if not _is_exporter_enabled():
        return
    process_id = pid if pid is not None else os.getpid()
    try:
        multiprocess.mark_process_dead(process_id)
    except Exception:
        logger.debug("Could not mark Celery worker process dead for Prometheus multiproc", exc_info=True)
