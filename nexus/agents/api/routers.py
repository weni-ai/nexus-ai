from django.urls import path
from nexus.agents.api.views import PushAgents


urlpatterns = [
    path('agents/push', PushAgents.as_view(), name="push-agents"),
]
