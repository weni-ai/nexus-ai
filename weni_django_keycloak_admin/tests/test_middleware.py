from unittest.mock import patch

from django.http import HttpResponse
from django.test import RequestFactory, SimpleTestCase, override_settings

from weni_django_keycloak_admin.middleware import AdminAuthorizationRefreshMiddleware


@override_settings(
    ROOT_URLCONF="nexus.urls",
    KEYCLOAK_ADMIN_OIDC={
        "ENABLED": True,
        "AUTHORIZATION_TTL_SECONDS": 300,
        "ADMIN_PATH": "/admin/",
    },
)
class AdminAuthorizationRefreshMiddlewareTest(SimpleTestCase):
    def setUp(self):
        self.middleware = AdminAuthorizationRefreshMiddleware(lambda request: HttpResponse("ok"))
        self.factory = RequestFactory()

    @patch("weni_django_keycloak_admin.middleware.time.time", return_value=1000)
    def test_expired_authorization_redirects_to_silent_revalidation(self, _time):
        request = self.factory.get("/admin/projects/")
        request.user = type("User", (), {"is_authenticated": True, "is_staff": True})()
        request.session = {"admin_oidc_authorized_at": 699}

        response = self.middleware(request)

        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/oidc/authenticate/", response.url)
        self.assertIn("reauth=1", response.url)

    @patch("weni_django_keycloak_admin.middleware.time.time", return_value=1000)
    def test_current_authorization_allows_admin_request(self, _time):
        request = self.factory.get("/admin/")
        request.user = type("User", (), {"is_authenticated": True, "is_staff": True})()
        request.session = {"admin_oidc_authorized_at": 900}

        response = self.middleware(request)

        self.assertEqual(response.status_code, 200)
