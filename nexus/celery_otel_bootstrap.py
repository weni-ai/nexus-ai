"""OpenTelemetry bootstrap for Celery workers **before** Django imports.

``django.setup()`` (and some Django integrations) install a concrete OpenTelemetry
``TracerProvider`` early. If Logfire runs after that, OpenTelemetry rejects replacing the
provider (\"Overriding of current TracerProvider is not allowed\").

**Important:** Langfuse ``get_client()`` only treats OpenTelemetry's built-in
``ProxyTracerProvider`` specially. Logfire exposes its own proxy that wraps an inner
``SDKTracerProvider``. Langfuse attaches ``LangfuseSpanProcessor`` to that inner provider via
the proxy's ``add_span_processor``.

If we replace the OTEL proxy with a plain ``SDKTracerProvider`` **before**
``logfire.configure()``, OTEL forbids swapping in Logfire's proxy. Instrumented spans then
hit Logfire's **internal** provider while Langfuse's processor stays on the **global** SDK
provider → shallow Langfuse traces (duplicate workflow rows, no Agent/LLM children).

Order in each **task process**: ``logfire.configure()`` first while the global tracer is
still the default OTEL proxy (or inherited from pre-Django bootstrap), then ``get_client()``
so Langfuse and Logfire share one export pipeline.

**Celery prefork:** Do **not** call ``get_client()`` in :func:`bootstrap_celery_otel_before_django`.
That runs in the **main** worker process before pool children fork. Langfuse's
``LangfuseSpanProcessor`` uses ``BatchSpanProcessor`` with a background export thread; after
``fork()`` that thread is invalid in children, so Langfuse often ingests nothing while Logfire
console output still looks fine. Use :func:`configure_logfire_openai_agents_otel` from
``worker_process_init`` (each pool child) and ``worker_ready`` (parent / solo).

Call :func:`bootstrap_celery_otel_before_django` from ``nexus/celery.py`` immediately after
setting ``DJANGO_SETTINGS_MODULE`` and **before** ``from django.conf import settings``.
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

_logfire_openai_agents_instrumented_pid: int | None = None


def bootstrap_logfire_before_django() -> None:
    """Set Logfire as the global OTEL provider before Django (no Langfuse, no instrument).

    Establishes Logfire's tracer proxy before ``django.setup()`` without starting Langfuse
    export threads in the prefork parent.
    """
    import logfire

    logfire.configure(
        service_name="openai-agents",
        send_to_logfire=False,
    )


def configure_logfire_openai_agents_otel(enabled: bool) -> None:
    """Configure Logfire and optionally Langfuse + OpenAI Agents once per OS process.

    Intended for Celery ``worker_process_init`` / ``worker_ready`` so Langfuse starts after
    fork in prefork pool children.
    """
    global _logfire_openai_agents_instrumented_pid

    import logfire
    from langfuse import get_client

    logfire.configure(
        service_name="openai-agents",
        send_to_logfire=False,
    )

    if enabled:
        try:
            get_client()
        except Exception:
            logger.exception("Failed to initialize Langfuse client for OTEL span processing.")

    if not enabled:
        return

    if _logfire_openai_agents_instrumented_pid == os.getpid():
        return

    logfire.instrument_openai_agents()
    _logfire_openai_agents_instrumented_pid = os.getpid()


def bootstrap_celery_otel_before_django() -> None:
    """Run Logfire-only setup before Django when running Celery (Langfuse deferred)."""
    _argv = " ".join(sys.argv).lower()
    if "celery" not in _argv:
        return
    try:
        bootstrap_logfire_before_django()
    except Exception:
        logger.exception("Failed Celery OTEL bootstrap (pre-Django).")
