from django.urls import path

from .resolution_criteria_views import (
    AIResolutionCriteriaDetailView,
    AIResolutionCriteriaListCreateView,
    AIResolutionCriteriaValidateView,
)
from .resolution_rate_views import ProjectsResolutionRateView
from .views import (
    AgentBuilderProjectDetailsView,
    AgentsBackendView,
    ConversationDetailProxyView,
    ConversationsExportProxyView,
    ConversationsProxyView,
    EnableHumanSupportView,
    FlowsDbCohortReconcileProxyView,
    ProjectPromptCreationConfigurationsViewset,
    ProjectUpdateViewset,
)

urlpatterns = [
    path("<project_uuid>/project", ProjectUpdateViewset.as_view(), name="project-update"),
    path(
        "<project_uuid>/prompt-creation-configurations",
        ProjectPromptCreationConfigurationsViewset.as_view(),
        name="project-prompt-creation-configurations",
    ),
    path("<project_uuid>/agents-backend", AgentsBackendView.as_view(), name="agents-backend"),
    path("<project_uuid>/human-support", EnableHumanSupportView.as_view(), name="enable-human-support"),
    path(
        "<project_uuid>/ai-resolution-criteria/",
        AIResolutionCriteriaListCreateView.as_view(),
        name="ai-resolution-criteria",
    ),
    path(
        "<project_uuid>/ai-validation-criteria/",
        AIResolutionCriteriaValidateView.as_view(),
        name="ai-validation-criteria",
    ),
    path(
        "<project_uuid>/ai-resolution-criteria/<criterion_id>/",
        AIResolutionCriteriaDetailView.as_view(),
        name="ai-resolution-criterion-detail",
    ),
    path("<project_uuid>/ab-project-details", AgentBuilderProjectDetailsView.as_view(), name="ab-project-details"),
    path("v2/projects/resolution-rate", ProjectsResolutionRateView.as_view(), name="projects-resolution-rate-v2"),
    path("v2/<project_uuid>/conversations", ConversationsProxyView.as_view(), name="conversations-proxy-v2"),
    path(
        "v2/<project_uuid>/conversations/export",
        ConversationsExportProxyView.as_view(),
        name="conversations-export-proxy-v2",
    ),
    path(
        "v2/<project_uuid>/conversations/<conversation_uuid>",
        ConversationDetailProxyView.as_view(),
        name="conversation-detail-proxy-v2",
    ),
    path(
        "v2/<project_uuid>/flows-db-cohort",
        FlowsDbCohortReconcileProxyView.as_view(),
        name="flows-db-cohort-reconcile-proxy-v2",
    ),
]
