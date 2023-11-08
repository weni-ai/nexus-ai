from django.urls import path, include
from rest_framework.routers import DefaultRouter
from .views import IntelligecesViewset

router = DefaultRouter()
router.register(r'', IntelligecesViewset, basename='intelligences')

urlpatterns = [
    path('<org_uuid>/intelligences/', include(router.urls)),
]
