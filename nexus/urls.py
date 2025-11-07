from django.contrib import admin
from django.urls import include, path
from django.http import HttpResponse

from rest_framework import permissions
from drf_yasg.views import get_schema_view
from drf_yasg import openapi

from nexus.intelligences.api.routers import urlpatterns as intelligence_routes
from nexus.actions.api.routers import urlpatterns as actions_routes
from nexus.analytics.api.routers import urlpatterns as analytics_routes
from nexus.projects.api.routers import urlpatterns as projects_routes
from nexus.logs.api.routers import urlpatterns as logs_routes
from nexus.zeroshot.api.routers import urlpatterns as zeroshot_routes
from nexus.agents.api.routers import urlpatterns as agent_routes
from nexus.users.api.urls import urlpatterns as users_routes

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
url_api += logs_routes
url_api += agent_routes
url_api += users_routes
url_api += analytics_routes

urlpatterns = [
    path("", lambda _: HttpResponse()),
    path("docs/", schema_view.with_ui("redoc")),
    path('admin/', admin.site.urls),
    path('api-auth/', include('rest_framework.urls')),
    path('api/', include(url_api)),
    path('v2/repository/', include(zeroshot_routes))
]
