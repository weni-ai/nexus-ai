from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    FlowsIntelligencesApiView,
    IntelligencesViewset,
    ContentBaseViewset,
    ContentBaseTextViewset,
    ContentBaseFileViewset,
)


org_router = DefaultRouter()
intelligence_router = DefaultRouter()
content_base_router = DefaultRouter()

org_router.register(r'', IntelligencesViewset, basename='intelligences')
intelligence_router.register(
    r'content-bases',
    ContentBaseViewset,
    basename='content-bases'
)
content_base_router.register(
    r'content-bases-text',
    ContentBaseTextViewset,
    basename='content-bases-text'
)

content_base_router.register(
    r'content-bases-file',
    ContentBaseFileViewset,
    basename='content-base-file'
)


urlpatterns = [
    path('<org_uuid>/intelligences/', include(org_router.urls)),
    path('<intelligence_uuid>/', include(intelligence_router.urls)),
    path('<content_base_uuid>/', include(content_base_router.urls)),
    path('v1/intelligences/content_bases/<project_uuid>/', FlowsIntelligencesApiView.as_view(), name="project-intelligences"),
]
