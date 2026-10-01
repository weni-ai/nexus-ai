import logging
from urllib.parse import urlencode

from django.contrib import auth
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.urls import reverse
from django.views import View
from mozilla_django_oidc.views import (
    OIDCAuthenticationCallbackView,
    OIDCAuthenticationRequestView,
)

from .config import get_config, get_oidc_setting
from .metrics import record_event

LOGGER = logging.getLogger("weni.keycloak_admin")


class AdminOIDCSettingsMixin:
    @staticmethod
    def get_settings(attr, *args):
        return get_oidc_setting(attr, *args)


class AdminOIDCAuthenticationRequestView(AdminOIDCSettingsMixin, OIDCAuthenticationRequestView):
    def get_extra_params(self, request):
        params = dict(super().get_extra_params(request))
        if request.GET.get("reauth") == "1":
            params.update({"prompt": "none", "max_age": "0"})
            record_event("revalidation_started")
        else:
            record_event("login_started")
        return params


class AdminOIDCAuthenticationCallbackView(AdminOIDCSettingsMixin, OIDCAuthenticationCallbackView):
    def login_failure(self):
        if self.request.user.is_authenticated:
            auth.logout(self.request)
        record_event("callback_failed")
        LOGGER.warning("Django Admin OIDC callback failed")
        return super().login_failure()


class AdminOIDCLogoutView(AdminOIDCSettingsMixin, View):
    http_method_names = ["post"]

    def post(self, request):
        config = get_config()
        logout_redirect = request.build_absolute_uri(config["LOGOUT_REDIRECT_URL"])
        params = urlencode(
            {
                "client_id": config["CLIENT_ID"],
                "post_logout_redirect_uri": logout_redirect,
            }
        )
        auth.logout(request)
        record_event("logout")
        return HttpResponseRedirect(f"{config['END_SESSION_ENDPOINT']}?{params}")

    def get(self, request):
        return HttpResponseNotAllowed(["POST"])


def admin_login_redirect(request):
    query = urlencode({"next": request.GET.get("next", "/admin/")})
    return HttpResponseRedirect(f"{reverse('admin_oidc_init')}?{query}")
