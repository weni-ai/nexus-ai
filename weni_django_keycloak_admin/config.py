from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

SETTING_NAME = "KEYCLOAK_ADMIN_OIDC"

OIDC_SETTING_MAP = {
    "OIDC_OP_AUTHORIZATION_ENDPOINT": "AUTHORIZATION_ENDPOINT",
    "OIDC_OP_TOKEN_ENDPOINT": "TOKEN_ENDPOINT",
    "OIDC_OP_USER_ENDPOINT": "USER_ENDPOINT",
    "OIDC_OP_JWKS_ENDPOINT": "JWKS_ENDPOINT",
    "OIDC_RP_CLIENT_ID": "CLIENT_ID",
    "OIDC_RP_CLIENT_SECRET": "CLIENT_SECRET",
    "OIDC_RP_SCOPES": "SCOPES",
    "OIDC_RP_SIGN_ALGO": "SIGN_ALGORITHM",
    "OIDC_TIMEOUT": "TIMEOUT_SECONDS",
    "OIDC_VERIFY_SSL": "VERIFY_SSL",
    "OIDC_USE_NONCE": "USE_NONCE",
    "OIDC_USE_PKCE": "USE_PKCE",
    "OIDC_STORE_ACCESS_TOKEN": "STORE_ACCESS_TOKEN",
    "OIDC_STORE_ID_TOKEN": "STORE_ID_TOKEN",
    "OIDC_AUTHENTICATION_CALLBACK_URL": "CALLBACK_URL_NAME",
    "OIDC_AUTH_REQUEST_EXTRA_PARAMS": "AUTH_REQUEST_EXTRA_PARAMS",
    "LOGIN_REDIRECT_URL": "LOGIN_REDIRECT_URL",
    "LOGIN_REDIRECT_URL_FAILURE": "LOGIN_FAILURE_URL",
    "LOGOUT_REDIRECT_URL": "LOGOUT_REDIRECT_URL",
}

DEFAULTS = {
    "SCOPES": "openid profile email",
    "SIGN_ALGORITHM": "RS256",
    "TIMEOUT_SECONDS": 5,
    "VERIFY_SSL": True,
    "USE_NONCE": True,
    "USE_PKCE": True,
    "STORE_ACCESS_TOKEN": False,
    "STORE_ID_TOKEN": False,
    "CALLBACK_URL_NAME": "admin_oidc_callback",
    "LOGIN_REDIRECT_URL": "/admin/",
    "LOGIN_FAILURE_URL": "/",
    "LOGOUT_REDIRECT_URL": "/",
    "AUTH_REQUEST_EXTRA_PARAMS": {},
    "AUTHORIZATION_TTL_SECONDS": 300,
    "REQUIRE_EMAIL_VERIFIED": True,
    "ENABLED": True,
}


def get_config():
    return {**DEFAULTS, **getattr(settings, SETTING_NAME, {})}


def get_oidc_setting(name, *default):
    config_key = OIDC_SETTING_MAP.get(name)
    if config_key:
        config = get_config()
        if config_key in config:
            return config[config_key]
    if default:
        return default[0]
    raise ImproperlyConfigured(f"{SETTING_NAME}.{config_key or name} must be configured")
