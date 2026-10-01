from prometheus_client import Counter

ADMIN_OIDC_EVENTS = Counter(
    "django_admin_oidc_events_total",
    "Django Admin OIDC authentication events.",
    ("event",),
)


def record_event(event):
    ADMIN_OIDC_EVENTS.labels(event=event).inc()
