from functools import partial

import sentry_sdk
from django.apps import AppConfig
from django.conf import settings
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from nexus.sentry.filters import filter_events


def traces_sampler(sampling_context):
    """
    Custom sampler for Sentry transactions.

    Always samples manual transactions (e.g., pre_generation.fetch_data)
    while keeping automatic instrumentation disabled (returns 0.0 for automatic transactions).

    Args:
        sampling_context: Context containing transaction information

    Returns:
        float: Sample rate (0.0 to 1.0)
    """
    # Get transaction context
    transaction_context = sampling_context.get("transaction_context", {})
    transaction_name = transaction_context.get("name", "")
    transaction_op = transaction_context.get("op", "")

    # Always sample manual transactions (pre_generation, observer, etc.)
    if transaction_name == "pre_generation.fetch_data":
        return 1.0  # 100% sampling for pre_generation transactions

    # Check for observer transactions (from SentryPerformanceMiddleware)
    if transaction_op == "observer.execute" or (transaction_name and transaction_name.startswith("observer.")):
        return 1.0  # 100% sampling for observer transactions

    # Check if sampled=True was explicitly set (manual transaction)
    # This handles cases where sampled=True is passed to start_transaction()
    if transaction_context.get("sampled") is True:
        return 1.0  # Always sample when explicitly requested

    # For all other transactions (automatic instrumentation from Django/Celery), don't sample
    # This keeps automatic instrumentation disabled
    return 0.0


class SentryConfig(AppConfig):
    name = "nexus.sentry"

    def ready(self) -> None:
        if not settings.USE_SENTRY:
            return

        if settings.USE_SENTRY:
            sentry_sdk.init(
                dsn=settings.SENTRY_URL,
                integrations=[
                    DjangoIntegration(),
                    CeleryIntegration(),
                ],
                environment=settings.ENVIRONMENT,
                before_send=partial(filter_events, events_to_filter=settings.FILTER_SENTRY_EVENTS),
                traces_sample_rate=0.0,  # Disable automatic instrumentation (use manual transactions)
                traces_sampler=traces_sampler,  # Custom sampler for manual transactions
            )
