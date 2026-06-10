from django.urls import path
from rest_framework.routers import DefaultRouter
from weni.feature_flags.views import FeatureFlagsWebhookView

from nexus.feature_flags.views import FeatureFlagsViewSet

router = DefaultRouter()
router.register(r"feature_flags", FeatureFlagsViewSet, basename="feature_flags")

urlpatterns = [
    path(
        "growthbook/",
        FeatureFlagsWebhookView.as_view(),
        name="feature-flags-webhook",
    ),
]
urlpatterns += router.urls
