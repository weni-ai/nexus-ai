from functools import partial

import sentry_sdk
from django.apps import AppConfig
from django.conf import settings
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration

from nexus.sentry.filters import filter_events


def traces_sampler(sampling_context):
    """Sample manual transactions and observer transactions, disable automatic instrumentation."""
    transaction_context = sampling_context.get("transaction_context", {})
    transaction_op = transaction_context.get("op", "")

    # Sample when explicitly requested (track_transaction) or observer transactions
    if transaction_context.get("sampled") is True:
        return 1.0

    if transaction_op == "observer.execute":
        return 1.0

    return 0.0


class SentryConfig(AppConfig):
    name = "nexus.sentry"

    def ready(self) -> None:
        if not settings.USE_SENTRY:
            return

        sentry_sdk.init(
            dsn=settings.SENTRY_URL,
            integrations=[DjangoIntegration(), CeleryIntegration()],
            environment=settings.ENVIRONMENT,
            before_send=partial(filter_events, events_to_filter=settings.FILTER_SENTRY_EVENTS),
            traces_sample_rate=0.0,
            traces_sampler=traces_sampler,
        )
