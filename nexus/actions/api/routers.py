from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FlowsViewset
)


flows_router = DefaultRouter()

flows_router.register(r'', FlowsViewset, basename='flows')

urlpatterns = [
    path('<project_uuid>/flows/', include(flows_router.urls)),
]