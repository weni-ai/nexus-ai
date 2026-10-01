from urllib.parse import urlparse

from django.conf import settings
from django.core.checks import Error, Warning, register

from .config import get_config

REQUIRED = (
    "ISSUER",
    "AUTHORIZATION_ENDPOINT",
    "TOKEN_ENDPOINT",
    "USER_ENDPOINT",
    "JWKS_ENDPOINT",
    "END_SESSION_ENDPOINT",
    "CLIENT_ID",
    "CLIENT_SECRET",
    "AUTHORIZED_ROLE",
)


@register()
def check_keycloak_admin_config(app_configs, **kwargs):
    config = get_config()
    if not config.get("ENABLED", True):
        return []

    messages = []
    for key in REQUIRED:
        if not config.get(key):
            messages.append(Error(f"KEYCLOAK_ADMIN_OIDC.{key} is required", id="keycloak_admin.E001"))

    for key in REQUIRED[:6]:
        value = config.get(key)
        if value and not settings.DEBUG and urlparse(value).scheme != "https":
            messages.append(Error(f"KEYCLOAK_ADMIN_OIDC.{key} must use HTTPS", id="keycloak_admin.E002"))

    backends = settings.AUTHENTICATION_BACKENDS
    if "django.contrib.auth.backends.ModelBackend" in backends:
        messages.append(Error("ModelBackend must not be enabled with Admin OIDC", id="keycloak_admin.E003"))
    if not config.get("VERIFY_SSL", True):
        messages.append(Warning("OIDC TLS verification is disabled", id="keycloak_admin.W001"))
    if config.get("SIGN_ALGORITHM") != "RS256":
        messages.append(Error("Only RS256 is supported for Admin OIDC", id="keycloak_admin.E004"))
    if config.get("AUTHORIZATION_TTL_SECONDS", 0) > 300:
        messages.append(Error("Admin authorization TTL must not exceed 300 seconds", id="keycloak_admin.E005"))
    return messages
