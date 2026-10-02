from django.test import SimpleTestCase, override_settings

from weni_django_keycloak_admin.checks import check_keycloak_admin_config


class KeycloakAdminChecksTest(SimpleTestCase):
    @override_settings(KEYCLOAK_ADMIN_OIDC={"ENABLED": True})
    def test_missing_required_settings_are_reported(self):
        errors = check_keycloak_admin_config(None)

        self.assertTrue(any(error.id == "keycloak_admin.E001" for error in errors))

    @override_settings(
        DEBUG=False,
        AUTHENTICATION_BACKENDS=["django.contrib.auth.backends.ModelBackend"],
        KEYCLOAK_ADMIN_OIDC={
            "ENABLED": True,
            "ISSUER": "https://keycloak.example/realms/weni",
            "AUTHORIZATION_ENDPOINT": "https://keycloak.example/auth",
            "TOKEN_ENDPOINT": "https://keycloak.example/token",
            "USER_ENDPOINT": "https://keycloak.example/userinfo",
            "JWKS_ENDPOINT": "https://keycloak.example/certs",
            "END_SESSION_ENDPOINT": "https://keycloak.example/logout",
            "CLIENT_ID": "admin",
            "CLIENT_SECRET": "secret",
            "AUTHORIZED_ROLE": "admin",
        },
    )
    def test_local_model_backend_is_rejected(self):
        errors = check_keycloak_admin_config(None)

        self.assertTrue(any(error.id == "keycloak_admin.E003" for error in errors))
