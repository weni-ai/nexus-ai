from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import (
    IntelligencesViewset,
    ContentBaseViewset,
    ContentBaseTextViewset
)

router = DefaultRouter()
router.register(r'', IntelligencesViewset, basename='intelligences')
router.register(r'content-bases', ContentBaseViewset, basename='content-bases')
router.register(
    r'content-bases-text',
    ContentBaseTextViewset,
    basename='content-bases-text'
)

urlpatterns = [
    path('<org_uuid>/intelligences/', include(router.urls)),
]
