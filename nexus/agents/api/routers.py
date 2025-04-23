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
from nexus.inline_agents.api.views import ProjectCredentialsView as InlineProjectCredentialsView
from nexus.inline_agents.api.views import VtexAppActiveAgentsView as VtexAppActiveInlineAgentsView
from nexus.inline_agents.api.views import VtexAppAgentsView as VtexAppInlineAgentsView
from nexus.inline_agents.api.views import VtexAppOfficialAgentsView as VtexAppOfficialInlineAgentsView
from nexus.inline_agents.api.views import VTexAppTeamView as VtexAppInlineTeamView
from nexus.inline_agents.api.views import VtexAppProjectCredentialsView as VtexAppInlineProjectCredentialsView
from nexus.inline_agents.api.views import ProjectComponentsView as InlineProjectComponentsView


urlpatterns = [
    path('agents/push', PushInlineAgents.as_view(), name="push-agents"),
    path('agents/teams/<project_uuid>', InlineTeamView.as_view(), name="teams"),
    path('agents/app-teams/<project_uuid>', VtexAppInlineTeamView.as_view(), name="vtex-teams"),
    path('agents/my-agents/<project_uuid>', InlineAgentsView.as_view(), name="my-agents"),
    path('agents/app-my-agents/<project_uuid>', VtexAppInlineAgentsView.as_view(), name="vtex-my-agents"),
    path('agents/official/<project_uuid>', InlineOfficialAgentsView.as_view(), name="official-agents"),
    path('agents/traces/', AgentTracesView.as_view(), name="traces"),
    path('agents/app-official/<project_uuid>', VtexAppOfficialInlineAgentsView.as_view(), name="vtex-official-agents"),
    path('project/<project_uuid>/assign/<str:agent_uuid>', ActiveInlineAgentsView.as_view(), name="assign-agents"),
    path('project/<project_uuid>/app-assign/<str:agent_uuid>', VtexAppActiveInlineAgentsView.as_view(), name="vtex-assign-agents"),
    path('project/<project_uuid>/credentials', InlineProjectCredentialsView.as_view(), name="project-credentials"),
    path('project/<project_uuid>/credentials/<str:agent_uuid>', InlineProjectCredentialsView.as_view(), name="project-credentials-update"),
    path('project/<project_uuid>/app-credentials', VtexAppInlineProjectCredentialsView.as_view(), name="vtex-project-credentials"),
    path('project/<project_uuid>/rationale', RationaleView.as_view(), name="project-rationale"),
    path('project/<project_uuid>/components', InlineProjectComponentsView.as_view(), name="project-components"),
]
