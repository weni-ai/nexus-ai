from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FlowsViewset,
    SearchFlowView,
    MessagePreviewView,
    GenerateActionNameView,
    TemplateActionView
)


flows_router = DefaultRouter()

flows_router.register(r'', FlowsViewset, basename='flows')
flows_router.register(r'template-actions', TemplateActionView, basename='template-actions')

urlpatterns = [
    path('<project_uuid>/flows/', include(flows_router.urls)),
    path('<project_uuid>/search-flows/', SearchFlowView.as_view()),
    path('<project_uuid>/preview/', MessagePreviewView.as_view()),
    path('<project_uuid>/generate-action-name/', GenerateActionNameView.as_view())
]
