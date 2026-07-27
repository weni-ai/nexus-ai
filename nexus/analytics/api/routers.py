from django.urls import path

from .views import (
    ProjectsByMotorView,
    ResolutionRateAverageView,
    ResolutionRateIndividualView,
    UnresolvedRateView,
)
from .latency_views import (
    InlineAgentLatencyOutliersView,
    InlineAgentLatencySummaryView,
    InlineAgentLatencyTimeseriesView,
)

urlpatterns = [
    # Average resolution rate
    path(
        "analytics/resolution-rate/average/",
        ResolutionRateAverageView.as_view(),
        name="resolution-rate-average",
    ),
    # Individual resolution rate
    path(
        "analytics/resolution-rate/individual/",
        ResolutionRateIndividualView.as_view(),
        name="resolution-rate-individual",
    ),
    # Unresolved rate
    path(
        "analytics/unresolved-rate/",
        UnresolvedRateView.as_view(),
        name="unresolved-rate",
    ),
    # Projects by motor
    path(
        "analytics/projects/by-motor/",
        ProjectsByMotorView.as_view(),
        name="projects-by-motor",
    ),
    path(
        "analytics/inline-agent-latency/summary/",
        InlineAgentLatencySummaryView.as_view(),
        name="inline-agent-latency-summary",
    ),
    path(
        "analytics/inline-agent-latency/timeseries/",
        InlineAgentLatencyTimeseriesView.as_view(),
        name="inline-agent-latency-timeseries",
    ),
    path(
        "analytics/inline-agent-latency/outliers/",
        InlineAgentLatencyOutliersView.as_view(),
        name="inline-agent-latency-outliers",
    ),
]
