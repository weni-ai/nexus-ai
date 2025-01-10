from django.urls import path
from nexus.agents.api.views import (
    ActiveAgentsViewSet,
    AgentsView,
    OfficialAgentsView,
    PushAgents,
    TeamViewset
)


urlpatterns = [
    path('agents/push', PushAgents.as_view(), name="push-agents"),
    # path('agents/assign/<str:agent_uuid>', ActiveAgentsViewSet.as_view(), name="assign-agents"),
    path('project/<project_uuid>/assign/<str:agent_uuid>', ActiveAgentsViewSet.as_view(), name="assign-agents"),
    path('agents/teams/<project_uuid>', TeamViewset.as_view(), name="teams"),
    path('agents/my-agents/<project_uuid>', AgentsView.as_view(), name="my-agents"),
    path('agents/official/<project_uuid>', OfficialAgentsView.as_view(), name="my-agents"),
]
