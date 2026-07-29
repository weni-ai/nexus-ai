from unittest import mock
from uuid import uuid4

from django.test import SimpleTestCase
from rest_framework.exceptions import PermissionDenied
from rest_framework.test import APIRequestFactory
from weni_commons.auth import WeniAuthContext

from nexus.authentication.weni_io import (
    HybridIOInternalPermission,
    HybridIOProjectPermission,
    WeniIOAuthViewMixin,
)


class _DummyView(WeniIOAuthViewMixin):
    kwargs = {}


class HybridIOProjectPermissionTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.permission = HybridIOProjectPermission()
        self.view = mock.Mock()
        self.view.kwargs = {"project_uuid": str(uuid4())}

    def test_jwt_with_project_uuid_allows(self):
        request = self.factory.get("/")
        request.auth = WeniAuthContext(
            project_uuid=str(uuid4()),
            user_email="io@example.com",
            token_type="jwt",
        )
        self.assertTrue(self.permission.has_permission(request, self.view))

    def test_jwt_without_project_uuid_denies(self):
        request = self.factory.get("/")
        request.auth = WeniAuthContext(user_email="io@example.com", token_type="jwt")
        self.assertFalse(self.permission.has_permission(request, self.view))

    def test_jwt_with_only_vtex_account_denies(self):
        request = self.factory.get("/")
        request.auth = WeniAuthContext(
            vtex_account="mystore",
            user_email="io@example.com",
            token_type="jwt",
        )
        self.assertFalse(self.permission.has_permission(request, self.view))

    @mock.patch("nexus.authentication.weni_io.ProjectPermission.has_permission", return_value=True)
    @mock.patch(
        "nexus.authentication.weni_io.CanCommunicateInternally.has_permission",
        return_value=False,
    )
    def test_keycloak_falls_back_to_project_permission(self, _mock_internal, mock_project_permission):
        request = self.factory.get("/")
        request.user = mock.Mock(is_authenticated=True)
        request.auth = WeniAuthContext(
            project_uuid=str(uuid4()),
            user_email="dash@example.com",
            token_type="keycloak",
        )
        self.assertTrue(self.permission.has_permission(request, self.view))
        mock_project_permission.assert_called_once()


class HybridIOInternalPermissionTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.permission = HybridIOInternalPermission()
        self.view = mock.Mock()

    def test_jwt_with_project_uuid_allows(self):
        request = self.factory.get("/")
        request.auth = WeniAuthContext(
            project_uuid=str(uuid4()),
            user_email="io@example.com",
            token_type="jwt",
        )
        self.assertTrue(self.permission.has_permission(request, self.view))

    def test_jwt_with_only_vtex_account_denies(self):
        request = self.factory.get("/")
        request.auth = WeniAuthContext(
            vtex_account="mystore",
            user_email="io@example.com",
            token_type="jwt",
        )
        self.assertFalse(self.permission.has_permission(request, self.view))

    @mock.patch(
        "nexus.authentication.weni_io.CanCommunicateInternally.has_permission",
        return_value=False,
    )
    @mock.patch(
        "nexus.authentication.weni_io.ExternalTokenPermission.has_permission",
        return_value=False,
    )
    def test_keycloak_without_internal_perm_denies(self, *_mocks):
        request = self.factory.get("/")
        request.auth = WeniAuthContext(
            project_uuid=str(uuid4()),
            user_email="dash@example.com",
            token_type="keycloak",
        )
        self.assertFalse(self.permission.has_permission(request, self.view))


class WeniIOAuthViewMixinTests(SimpleTestCase):
    def setUp(self):
        self.factory = APIRequestFactory()
        self.view = _DummyView()
        self.project_uuid = str(uuid4())

    def test_uses_self_auth_project_uuid(self):
        request = self.factory.get("/")
        request.auth = WeniAuthContext(project_uuid=self.project_uuid, token_type="jwt")
        self.view.request = request
        self.view.kwargs = {"project_uuid": self.project_uuid}
        self.assertEqual(self.view.get_scoped_project_uuid(), self.project_uuid)

    def test_mismatch_between_path_and_token_raises_403(self):
        request = self.factory.get("/")
        request.auth = WeniAuthContext(project_uuid=self.project_uuid, token_type="jwt")
        self.view.request = request
        self.view.kwargs = {"project_uuid": str(uuid4())}
        with self.assertRaises(PermissionDenied):
            self.view.get_scoped_project_uuid()

    def test_jwt_without_project_uuid_raises_403_without_path_fallback(self):
        request = self.factory.get("/")
        request.auth = WeniAuthContext(vtex_account="mystore", token_type="jwt")
        self.view.request = request
        self.view.kwargs = {"project_uuid": self.project_uuid}
        with self.assertRaises(PermissionDenied):
            self.view.get_scoped_project_uuid()

    def test_keycloak_uses_auth_project_uuid(self):
        request = self.factory.get("/")
        request.auth = WeniAuthContext(project_uuid=self.project_uuid, token_type="keycloak")
        self.view.request = request
        self.view.kwargs = {"project_uuid": self.project_uuid}
        self.assertEqual(self.view.get_scoped_project_uuid(), self.project_uuid)

    def test_falls_back_to_path_only_without_auth_context(self):
        request = self.factory.get("/")
        request.auth = None
        self.view.request = request
        self.assertEqual(self.view.get_scoped_project_uuid(self.project_uuid), self.project_uuid)
