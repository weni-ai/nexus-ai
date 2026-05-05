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

Order here: ``logfire.configure()`` first while the global tracer is still the default OTEL
proxy (or unset), then ``get_client()`` so Langfuse and Logfire share one export pipeline.

Call :func:`bootstrap_celery_otel_before_django` from ``nexus/celery.py`` immediately after
setting ``DJANGO_SETTINGS_MODULE`` and **before** ``from django.conf import settings``.
"""

from __future__ import annotations

import logging
import os
import sys

logger = logging.getLogger(__name__)

_logfire_openai_agents_instrumented_pid: int | None = None


def _env_bool_enabled(name: str, default: bool = False) -> bool:
    """Match django-environ style truthy strings for deployment parity."""
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in ("1", "true", "yes", "on")


def configure_logfire_openai_agents_otel(enabled: bool) -> None:
    """Configure Logfire and optionally instrument OpenAI Agents once per OS process."""
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
    """Run Langfuse + Logfire setup before Django loads when running Celery."""
    _argv = " ".join(sys.argv).lower()
    if "celery" not in _argv:
        return
    enabled = _env_bool_enabled("ENABLE_LOGFIRE_OPENAI_AGENTS")
    try:
        configure_logfire_openai_agents_otel(enabled)
    except Exception:
        logger.exception("Failed Celery OTEL bootstrap (pre-Django).")
