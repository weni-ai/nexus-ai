from django.urls import path

from nexus.agents.api.views import AgentTracesView, DeleteAgentView, RationaleView
from nexus.inline_agents.api.views import ActiveAgentsView as ActiveInlineAgentsView
from nexus.inline_agents.api.views import (
    AgentBuilderAudio,
    AgentEndSessionView,
    AgentManagersView,
    LogGroupView,
    MultiAgentView,
    OfficialAgentDetailV1,
    OfficialAgentsV1,
)
from nexus.inline_agents.api.views import AgentsView as InlineAgentsView
from nexus.inline_agents.api.views import OfficialAgentsView as InlineOfficialAgentsView
from nexus.inline_agents.api.views import ProjectComponentsView as InlineProjectComponentsView
from nexus.inline_agents.api.views import ProjectCredentialsView as InlineProjectCredentialsView
from nexus.inline_agents.api.views import PushAgents as PushInlineAgents
from nexus.inline_agents.api.views import TeamView as InlineTeamView
from nexus.inline_agents.api.views import VtexAppActiveAgentsView as VtexAppActiveInlineAgentsView
from nexus.inline_agents.api.views import VtexAppAgentsView as VtexAppInlineAgentsView
from nexus.inline_agents.api.views import VtexAppOfficialAgentsView as VtexAppOfficialInlineAgentsView
from nexus.inline_agents.api.views import VtexAppProjectCredentialsView as VtexAppInlineProjectCredentialsView
from nexus.inline_agents.api.views import VTexAppTeamView as VtexAppInlineTeamView
from nexus.reports.views import ReportView

urlpatterns = [
    path("agents/push", PushInlineAgents.as_view(), name="push-agents"),
    path("v1/official/agents", OfficialAgentsV1.as_view(), name="v1-official-agents"),
    path("v1/official/agents/<agent_uuid>", OfficialAgentDetailV1.as_view(), name="v1-official-agent-detail"),
    path("agents/teams/<project_uuid>", InlineTeamView.as_view(), name="teams"),
    path("agents/app-teams/<project_uuid>", VtexAppInlineTeamView.as_view(), name="vtex-teams"),
    path("agents/my-agents/<project_uuid>", InlineAgentsView.as_view(), name="my-agents"),
    path("agents/app-my-agents/<project_uuid>", VtexAppInlineAgentsView.as_view(), name="vtex-my-agents"),
    path("agents/official/<project_uuid>", InlineOfficialAgentsView.as_view(), name="official-agents"),
    path("agents/traces/", AgentTracesView.as_view(), name="traces"),
    path("agents/app-official/<project_uuid>", VtexAppOfficialInlineAgentsView.as_view(), name="vtex-official-agents"),
    path("project/<project_uuid>/assign/<str:agent_uuid>", ActiveInlineAgentsView.as_view(), name="assign-agents"),
    path(
        "project/<project_uuid>/app-assign/<str:agent_uuid>",
        VtexAppActiveInlineAgentsView.as_view(),
        name="vtex-assign-agents",
    ),
    path("project/<project_uuid>/credentials", InlineProjectCredentialsView.as_view(), name="project-credentials"),
    path(
        "project/<project_uuid>/credentials/<str:agent_uuid>",
        InlineProjectCredentialsView.as_view(),
        name="project-credentials-update",
    ),
    path(
        "project/<project_uuid>/app-credentials",
        VtexAppInlineProjectCredentialsView.as_view(),
        name="vtex-project-credentials",
    ),
    path("project/<project_uuid>/rationale", RationaleView.as_view(), name="project-rationale"),
    path("project/<project_uuid>/components", InlineProjectComponentsView.as_view(), name="project-components"),
    path("project/<project_uuid>/multi-agents", MultiAgentView.as_view(), name="multi-agents"),
    path("project/<project_uuid>/end-session", AgentEndSessionView.as_view(), name="end-session"),
    path("project/<project_uuid>/multi-agents-audio", AgentBuilderAudio.as_view(), name="multi-agents-audio"),
    path("agents/log-group", LogGroupView.as_view(), name="agents-log-group"),
    path("reports", ReportView.as_view(), name="reports"),
    path("project/<project_uuid>/agents/<str:agent_uuid>", DeleteAgentView.as_view(), name="delete-agent"),
    path("project/<project_uuid>/managers", AgentManagersView.as_view(), name="project-agent-managers"),
]
