from django.contrib import admin
from django.http import HttpResponse
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularRedocView,
    SpectacularSwaggerView,
)

from nexus.actions.api.routers import urlpatterns as actions_routes
from nexus.agents.api.routers import urlpatterns as agent_routes
from nexus.analytics.api.routers import urlpatterns as analytics_routes
from nexus.intelligences.api.routers import urlpatterns as intelligence_routes
from nexus.logs.api.routers import urlpatterns as logs_routes
from nexus.projects.api.routers import urlpatterns as projects_routes
from nexus.users.api.urls import urlpatterns as users_routes
from nexus.zeroshot.api.routers import urlpatterns as zeroshot_routes

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
    path("schema/", SpectacularAPIView.as_view(), name="schema"),
    path("swagger/", SpectacularSwaggerView.as_view(url_name="schema")),
    path("docs/", SpectacularRedocView.as_view(url_name="schema")),
    path("admin/", admin.site.urls),
    path("api-auth/", include("rest_framework.urls")),
    path("api/", include(url_api)),
    path("v2/repository/", include(zeroshot_routes)),
]
