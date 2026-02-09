from django.urls import path

from .views import (
    AgentBuilderProjectDetailsView,
    AgentsBackendView,
    ConversationsProxyView,
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
    path("<project_uuid>/ab-project-details", AgentBuilderProjectDetailsView.as_view(), name="ab-project-details"),
    path("v2/<project_uuid>/conversations", ConversationsProxyView.as_view(), name="conversations-proxy-v2"),
]
