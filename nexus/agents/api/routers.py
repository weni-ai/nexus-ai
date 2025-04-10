from django.urls import path
from nexus.agents.api.views import (
    ActiveAgentsViewSet,
    AgentTracesView,
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
    RationaleView,
)

from nexus.inline_agents.api.views import PushAgents as PushInlineAgents
from nexus.inline_agents.api.views import ActiveAgentsView as ActiveInlineAgentsView
from nexus.inline_agents.api.views import TeamView as InlineTeamView
from nexus.inline_agents.api.views import AgentsView as InlineAgentsView
from nexus.inline_agents.api.views import OfficialAgentsView as InlineOfficialAgentsView


urlpatterns = [
    path('agents/push', PushInlineAgents.as_view(), name="push-agents"),
    path('agents/teams/<project_uuid>', InlineTeamView.as_view(), name="teams"),
    path('agents/app-teams/<project_uuid>', VTexAppTeamView.as_view(), name="vtex-teams"),
    path('agents/my-agents/<project_uuid>', InlineAgentsView.as_view(), name="my-agents"),
    path('agents/app-my-agents/<project_uuid>', VtexAppAgentsView.as_view(), name="vtex-my-agents"),
    path('agents/official/<project_uuid>', InlineOfficialAgentsView.as_view(), name="official-agents"),
    path('agents/traces/', AgentTracesView.as_view(), name="traces"),
    path('agents/official/<project_uuid>', VtexAppOfficialAgentsView.as_view(), name="vtex-official-agents"),
    path('agents/app-official/<project_uuid>', VtexAppOfficialAgentsView.as_view(), name="vtex-official-agents"),
    path('project/<project_uuid>/assign/<str:agent_uuid>', ActiveInlineAgentsView.as_view(), name="assign-agents"),
    path('project/<project_uuid>/app-assign/<str:agent_uuid>', VtexAppActiveAgentsViewSet.as_view(), name="vtex-assign-agents"),
    path('project/<project_uuid>/credentials', ProjectCredentialsView.as_view(), name="project-credentials"),
    path('project/<project_uuid>/credentials/<str:agent_uuid>', ProjectCredentialsView.as_view(), name="project-credentials-update"),
    path('project/<project_uuid>/app-credentials', VtexAppProjectCredentialsView.as_view(), name="vtex-project-credentials"),
    path('project/<project_uuid>/rationale', RationaleView.as_view(), name="project-rationale"),
]
