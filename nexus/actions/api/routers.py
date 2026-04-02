from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    FlowsViewset,
    GenerateActionNameView,
    MessagePreviewView,
    MessageSimulationView,
    SearchFlowView,
    SimulationEndSessionView,
    SimulationManagerModelView,
    TemplateActionView,
)

flows_router = DefaultRouter()

flows_router.register(r"", FlowsViewset, basename="flows")

template_action_router = DefaultRouter()
template_action_router.register(r"template-action", TemplateActionView, basename="template-action")

urlpatterns = [
    path("<project_uuid>/flows/", include(flows_router.urls)),
    path("<project_uuid>/search-flows/", SearchFlowView.as_view()),
    path("<project_uuid>/preview/", MessagePreviewView.as_view()),
    path("<project_uuid>/simulation/", MessageSimulationView.as_view()),
    path("<project_uuid>/simulation/end-session/", SimulationEndSessionView.as_view()),
    path("<project_uuid>/simulation/manager-model/", SimulationManagerModelView.as_view()),
    path("<project_uuid>/generate-action-name/", GenerateActionNameView.as_view()),
    path("<project_uuid>/", include(template_action_router.urls)),
]
