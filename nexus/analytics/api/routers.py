from django.urls import path

from .views import (
    ResolutionRateAverageView,
    ResolutionRateIndividualView,
    UnresolvedRateView,
    ProjectsByMotorView,
)

urlpatterns = [
    # Average resolution rate (global endpoint, project_uuid optional via query param)
    path(
        "analytics/resolution-rate/average/",
        ResolutionRateAverageView.as_view(),
        name="resolution-rate-average",
    ),
<<<<<<< HEAD
    # Individual resolution rate (global endpoint, project_uuid optional via query param)
=======
    # Individual resolution rate
>>>>>>> 2cd4d5b4 (change endpoints to be global scoped)
    path(
        "analytics/resolution-rate/individual/",
        ResolutionRateIndividualView.as_view(),
        name="resolution-rate-individual",
    ),
    # Unresolved rate (global endpoint, project_uuid optional via query param)
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
]
