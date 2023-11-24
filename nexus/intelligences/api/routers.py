from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import IntelligencesViewset

router = DefaultRouter()
router.register(r'', IntelligencesViewset, basename='intelligences')

urlpatterns = [
    path('<org_uuid>/intelligences/', include(router.urls)),
]
