from django.urls import path

from .views import (
    AdminOIDCAuthenticationCallbackView,
    AdminOIDCAuthenticationRequestView,
    AdminOIDCLogoutView,
)

urlpatterns = [
    path("authenticate/", AdminOIDCAuthenticationRequestView.as_view(), name="admin_oidc_init"),
    path("callback/", AdminOIDCAuthenticationCallbackView.as_view(), name="admin_oidc_callback"),
    path("logout/", AdminOIDCLogoutView.as_view(), name="admin_oidc_logout"),
]
