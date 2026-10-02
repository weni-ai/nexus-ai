import json
import time
from unittest.mock import patch

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from django.core.exceptions import SuspiciousOperation
from django.test import TestCase, override_settings

from nexus.users.models import User
from weni_django_keycloak_admin.backend import AdminOIDCBackend

CONFIG = {
    "CLIENT_ID": "nexus-ai-admin",
    "CLIENT_SECRET": "secret",
    "ISSUER": "https://keycloak.example/realms/weni",
    "AUTHORIZED_ROLE": "nexus-ai-admin",
    "SIGN_ALGORITHM": "RS256",
    "REQUIRE_EMAIL_VERIFIED": True,
    "USE_NONCE": True,
    "SCOPES": "openid profile email",
}


@override_settings(KEYCLOAK_ADMIN_OIDC=CONFIG)
class AdminOIDCBackendTest(TestCase):
    def setUp(self):
        self.backend = AdminOIDCBackend.__new__(AdminOIDCBackend)
        self.backend.UserModel = User
        self.backend.request = type("Request", (), {"session": {}})()
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    @staticmethod
    def claims(roles=None, **overrides):
        claims = {
            "sub": "keycloak-subject",
            "email": "admin@example.com",
            "email_verified": True,
            "resource_access": {"nexus-ai-admin": {"roles": roles or ["nexus-ai-admin"]}},
        }
        claims.update(overrides)
        return claims

    @patch("mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_claims", return_value=True)
    def test_authorized_claims_create_superuser_with_unusable_password(self, _verify):
        claims = self.claims()

        self.assertTrue(self.backend.verify_claims(claims))
        user = self.backend.create_user(claims)

        self.assertTrue(user.is_staff)
        self.assertTrue(user.is_superuser)
        self.assertFalse(user.has_usable_password())
        self.assertEqual(self.backend.request.session["admin_oidc_subject"], "keycloak-subject")

    @patch("mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_claims", return_value=True)
    def test_missing_role_denies_and_removes_existing_admin_access(self, _verify):
        user = User.objects.create_user(email="admin@example.com", is_superuser=True)

        verified = self.backend.verify_claims(self.claims(roles=["other-role"]))

        self.assertFalse(verified)
        user.refresh_from_db()
        self.assertFalse(user.is_superuser)

    @patch("mozilla_django_oidc.auth.OIDCAuthenticationBackend.verify_claims", return_value=True)
    def test_unverified_email_is_denied(self, _verify):
        self.assertFalse(self.backend.verify_claims(self.claims(email_verified=False)))

    @patch("mozilla_django_oidc.auth.OIDCAuthenticationBackend.get_userinfo")
    def test_id_token_claims_are_merged_into_userinfo(self, get_userinfo):
        get_userinfo.return_value = {"email": "admin@example.com"}

        claims = self.backend.get_userinfo("access", "id", {"sub": "subject", "resource_access": {}})

        self.assertEqual(claims["sub"], "subject")
        self.assertEqual(claims["email"], "admin@example.com")

    def token(self, **overrides):
        now = int(time.time())
        payload = {
            "sub": "subject",
            "iss": CONFIG["ISSUER"],
            "aud": CONFIG["CLIENT_ID"],
            "azp": CONFIG["CLIENT_ID"],
            "iat": now,
            "exp": now + 60,
            "nonce": "expected-nonce",
        }
        payload.update(overrides)
        return jwt.encode(payload, self.private_key, algorithm="RS256")

    def jwk(self):
        return json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(self.private_key.public_key()))

    def test_verify_token_passes_bytes_to_jwk_lookup(self):
        with patch.object(self.backend, "retrieve_matching_jwk", return_value=self.jwk()) as lookup:
            self.backend.verify_token(self.token(), nonce="expected-nonce")

        self.assertIsInstance(lookup.call_args.args[0], bytes)

    def test_verify_token_validates_issuer_audience_and_nonce(self):
        with patch.object(self.backend, "retrieve_matching_jwk", return_value=self.jwk()):
            payload = self.backend.verify_token(self.token(), nonce="expected-nonce")

        self.assertEqual(payload["sub"], "subject")

    def test_verify_token_rejects_wrong_issuer(self):
        with (
            patch.object(self.backend, "retrieve_matching_jwk", return_value=self.jwk()),
            self.assertRaises(SuspiciousOperation),
        ):
            self.backend.verify_token(self.token(iss="https://attacker.example"), nonce="expected-nonce")

    def test_verify_token_rejects_wrong_audience(self):
        with (
            patch.object(self.backend, "retrieve_matching_jwk", return_value=self.jwk()),
            self.assertRaises(SuspiciousOperation),
        ):
            self.backend.verify_token(self.token(aud="another-client"), nonce="expected-nonce")
