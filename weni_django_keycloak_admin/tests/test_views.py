from urllib.parse import parse_qs, urlparse

from django.test import TestCase, override_settings

from nexus.users.models import User

CONFIG = {
    "ENABLED": True,
    "ISSUER": "https://keycloak.example/realms/weni",
    "AUTHORIZATION_ENDPOINT": "https://keycloak.example/realms/weni/protocol/openid-connect/auth",
    "TOKEN_ENDPOINT": "https://keycloak.example/realms/weni/protocol/openid-connect/token",
    "USER_ENDPOINT": "https://keycloak.example/realms/weni/protocol/openid-connect/userinfo",
    "JWKS_ENDPOINT": "https://keycloak.example/realms/weni/protocol/openid-connect/certs",
    "END_SESSION_ENDPOINT": "https://keycloak.example/realms/weni/protocol/openid-connect/logout",
    "CLIENT_ID": "nexus-ai-admin",
    "CLIENT_SECRET": "secret",
    "AUTHORIZED_ROLE": "nexus-ai-admin",
}


@override_settings(KEYCLOAK_ADMIN_OIDC=CONFIG)
class AdminOIDCViewsTest(TestCase):
    def test_admin_login_redirects_to_oidc_flow_without_local_form(self):
        response = self.client.get("/admin/login/?next=/admin/projects/")

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, "/admin/oidc/authenticate/?next=%2Fadmin%2Fprojects%2F")

    def test_oidc_authentication_uses_dedicated_client_and_pkce(self):
        response = self.client.get("/admin/oidc/authenticate/?next=/admin/")

        self.assertEqual(response.status_code, 302)
        query = parse_qs(urlparse(response.url).query)
        self.assertEqual(query["client_id"], ["nexus-ai-admin"])
        self.assertEqual(query["response_type"], ["code"])
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["redirect_uri"], ["http://testserver/admin/oidc/callback/"])

    def test_logout_is_post_only_and_redirects_to_keycloak(self):
        user = User.objects.create_user(email="admin@example.com", is_superuser=True)
        self.client.force_login(user)

        self.assertEqual(self.client.get("/admin/logout/").status_code, 405)
        response = self.client.post("/admin/logout/")

        self.assertEqual(response.status_code, 302)
        parsed = urlparse(response.url)
        self.assertEqual(parsed.path, "/realms/weni/protocol/openid-connect/logout")
        self.assertEqual(parse_qs(parsed.query)["client_id"], ["nexus-ai-admin"])
        self.assertNotIn("_auth_user_id", self.client.session)
