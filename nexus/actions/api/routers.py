from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FlowsViewset,
    SearchFlowView
)


flows_router = DefaultRouter()

flows_router.register(r'', FlowsViewset, basename='flows')

urlpatterns = [
    path('<project_uuid>/flows/', include(flows_router.urls)),
    path('<project_uuid>/search-flows/', SearchFlowView.as_view()),
]
