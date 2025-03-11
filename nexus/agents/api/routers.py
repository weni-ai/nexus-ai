from django.urls import path
from nexus.agents.api.views import (
    ActiveAgentsViewSet,
    AgentsView,
    PushAgents,
    TeamView,
    OfficialAgentsView,
    ProjectCredentialsView,
    VtexAppActiveAgentsViewSet,
    VtexAppAgentsView,
    VtexAppOfficialAgentsView,
    VTexAppTeamView,
    VtexAppProjectCredentialsView,
)


urlpatterns = [
    path('agents/push', PushAgents.as_view(), name="push-agents"),
    path('agents/teams/<project_uuid>', TeamView.as_view(), name="teams"),
    path('agents/app-teams/<project_uuid>', VTexAppTeamView.as_view(), name="vtex-teams"),
    path('agents/my-agents/<project_uuid>', AgentsView.as_view(), name="my-agents"),
    path('agents/app-my-agents/<project_uuid>', VtexAppAgentsView.as_view(), name="vtex-my-agents"),
    path('agents/official/<project_uuid>', OfficialAgentsView.as_view(), name="official-agents"),
    path('agents/app-official/<project_uuid>', VtexAppOfficialAgentsView.as_view(), name="vtex-official-agents"),
    path('project/<project_uuid>/assign/<str:agent_uuid>', ActiveAgentsViewSet.as_view(), name="assign-agents"),
    path('project/<project_uuid>/app-assign/<str:agent_uuid>', VtexAppActiveAgentsViewSet.as_view(), name="vtex-assign-agents"),
    path('project/<project_uuid>/credentials', ProjectCredentialsView.as_view(), name="project-credentials"),
    path('project/<project_uuid>/credentials/<str:agent_uuid>', ProjectCredentialsView.as_view(), name="project-credentials-update"),
    path('project/<project_uuid>/app-credentials', VtexAppProjectCredentialsView.as_view(), name="vtex-project-credentials"),
]
