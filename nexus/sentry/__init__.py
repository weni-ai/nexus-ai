import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration
from nexus.sentry.filters import filter_events

from django.conf import settings


if settings.USE_SENTRY:
    sentry_sdk.init(
        dsn=settings.SENTRY_URL,
        integrations=[DjangoIntegration()],
        environment=settings.ENVIRONMENT,
        before_send=filter_events
    )
