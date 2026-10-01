import time
from urllib.parse import urlencode

from django.http import HttpResponseRedirect
from django.urls import reverse

from .config import get_config


class AdminAuthorizationRefreshMiddleware:
    """Force a silent OIDC round trip when the authorization lease expires."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        config = get_config()
        admin_path = config.get("ADMIN_PATH", "/admin/")
        exempt_paths = (
            f"{admin_path}login/",
            f"{admin_path}logout/",
            f"{admin_path}oidc/",
        )
        if (
            config.get("ENABLED", True)
            and request.path.startswith(admin_path)
            and not request.path.startswith(exempt_paths)
            and request.user.is_authenticated
            and getattr(request.user, "is_staff", False)
        ):
            authorized_at = request.session.get("admin_oidc_authorized_at", 0)
            if time.time() - authorized_at >= config["AUTHORIZATION_TTL_SECONDS"]:
                query = urlencode({"next": request.get_full_path(), "reauth": "1"})
                return HttpResponseRedirect(f"{reverse('admin_oidc_init')}?{query}")
        return self.get_response(request)
