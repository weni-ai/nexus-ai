"""OpenTelemetry bootstrap for Celery workers **before** Django imports.

``django.setup()`` (and some Django integrations) install a concrete OpenTelemetry
``TracerProvider`` early. If Logfire runs after that, OpenTelemetry rejects replacing the
provider (\"Overriding of current TracerProvider is not allowed\") and nested spans may
never reach Langfuse.

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


def _ensure_sdk_tracer_provider_when_still_proxy() -> None:
    """Install a real SDK TracerProvider before Django locks OTEL (Logfire path only).

    While the global provider is still ``ProxyTracerProvider``, ``django.setup()`` will
    typically replace it with its own ``TracerProvider``. After that, subsequent libraries
    cannot take ownership of the provider chain reliably.

    Installing one SDK ``TracerProvider`` here (with ``service.name``) lets Langfuse attach
    ``LangfuseSpanProcessor`` to the same provider Logfire instruments, and Django's later
    ``set_tracer_provider`` call becomes a no-op (OTEL refuses overrides).
    """
    from opentelemetry import trace as otel_trace_api
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider

    current = otel_trace_api.get_tracer_provider()
    if not isinstance(current, otel_trace_api.ProxyTracerProvider):
        return
    resource = Resource.create({"service.name": "openai-agents"})
    otel_trace_api.set_tracer_provider(SDKTracerProvider(resource=resource))


def configure_logfire_openai_agents_otel(enabled: bool) -> None:
    """Configure Logfire and optionally instrument OpenAI Agents once per OS process."""
    global _logfire_openai_agents_instrumented_pid

    import logfire
    from langfuse import get_client

    if enabled:
        # Replace ProxyTracerProvider before Django so Langfuse attaches LangfuseSpanProcessor
        # to this SDK provider; django.setup() cannot replace it afterward.
        _ensure_sdk_tracer_provider_when_still_proxy()
        try:
            get_client()
        except Exception:
            logger.exception("Failed to initialize Langfuse client for OTEL span processing.")

    # Logfire may log \"Overriding TracerProvider is not allowed\" if the SDK provider is
    # already set; spans still merge onto the active provider.
    logfire.configure(
        service_name="openai-agents",
        send_to_logfire=False,
    )

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
