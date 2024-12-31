from django.urls import path
from nexus.agents.api.views import (
    PushAgents,
    ActiveAgentsViewSet,
    TeamViewset
)


urlpatterns = [
    path('agents/push', PushAgents.as_view(), name="push-agents"),
    path('agents/assign/<str:agent_uuid>', ActiveAgentsViewSet.as_view(), name="assign-agents"),
    path('agents/teams/<project_uuid>', TeamViewset.as_view(), name="teams"),
]
