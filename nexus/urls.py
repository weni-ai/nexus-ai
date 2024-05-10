from django.contrib import admin
from django.urls import include, path
from rest_framework import permissions

from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from nexus.intelligences.api.routers import urlpatterns as intelligence_routes
from nexus.actions.api.routers import urlpatterns as actions_routes
from nexus.projects.api.routers import urlpatterns as projects_routes


schema_view = get_schema_view(
    openapi.Info(
        title="API Documentation",
        default_version="v1.0.0",
        license=openapi.License(name="GPL-3.0 License"),
    ),
    public=True,
    permission_classes=(permissions.AllowAny,),
)

url_api = []

url_api += intelligence_routes
url_api += actions_routes
url_api += projects_routes


def vi(request):
    raise OverflowError


urlpatterns = [
    path("", schema_view.with_ui("redoc")),
    path('admin/', admin.site.urls),
    path('api-auth/', include('rest_framework.urls')),
    path('api/', include(url_api)),
    path('sentry-debug', vi)
]
