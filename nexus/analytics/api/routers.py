from django.urls import path

from .views import (
    ResolutionRateAverageView,
    ResolutionRateIndividualView,
    UnresolvedRateView,
    ProjectsByMotorView,
)

urlpatterns = [
    # Average resolution rate
    path(
        "<project_uuid>/analytics/resolution-rate/average/",
        ResolutionRateAverageView.as_view(),
        name="resolution-rate-average",
    ),
    # Individual resolution rate (per project)
    path(
        "<project_uuid>/analytics/resolution-rate/individual/",
        ResolutionRateIndividualView.as_view(),
        name="resolution-rate-individual",
    ),
    # Unresolved rate
    path(
        "<project_uuid>/analytics/unresolved-rate/",
        UnresolvedRateView.as_view(),
        name="unresolved-rate",
    ),
    # Projects by motor (global, no project_uuid)
    path(
        "analytics/projects/by-motor/",
        ProjectsByMotorView.as_view(),
        name="projects-by-motor",
    ),
]

