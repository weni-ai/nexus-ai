import logging
import time

import jwt
from django.core.exceptions import SuspiciousOperation
from django.utils.encoding import force_bytes
from mozilla_django_oidc.auth import OIDCAuthenticationBackend

from .config import get_config, get_oidc_setting
from .metrics import record_event

LOGGER = logging.getLogger("weni.keycloak_admin")


class AdminOIDCBackend(OIDCAuthenticationBackend):
    """OIDC backend that grants all-or-nothing Django Admin access."""

    @staticmethod
    def get_settings(attr, *args):
        return get_oidc_setting(attr, *args)

    def verify_token(self, token, **kwargs):
        key_data = self.retrieve_matching_jwk(force_bytes(token))
        key = jwt.PyJWK.from_dict(key_data).key
        config = get_config()
        try:
            payload = jwt.decode(
                token,
                key,
                algorithms=[config["SIGN_ALGORITHM"]],
                audience=config["CLIENT_ID"],
                issuer=config["ISSUER"],
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
        except jwt.PyJWTError as exc:
            record_event("invalid_token")
            raise SuspiciousOperation("OIDC token validation failed") from exc

        if config.get("USE_NONCE", True) and payload.get("nonce") != kwargs.get("nonce"):
            record_event("invalid_nonce")
            raise SuspiciousOperation("OIDC token nonce validation failed")

        authorized_party = payload.get("azp")
        if authorized_party and authorized_party != config["CLIENT_ID"]:
            record_event("invalid_authorized_party")
            raise SuspiciousOperation("OIDC token authorized party validation failed")

        return payload

    def get_userinfo(self, access_token, id_token, payload):
        userinfo = super().get_userinfo(access_token, id_token, payload)
        # Keycloak role mappers must include the client role in the ID token.
        return {**userinfo, **payload}

    def verify_claims(self, claims):
        config = get_config()
        client_roles = claims.get("resource_access", {}).get(config["CLIENT_ID"], {}).get("roles", [])
        email_verified = claims.get("email_verified") is True
        authorized = config["AUTHORIZED_ROLE"] in client_roles
        verified = (
            super().verify_claims(claims)
            and bool(claims.get("sub"))
            and authorized
            and (email_verified or not config.get("REQUIRE_EMAIL_VERIFIED", True))
        )
        if not verified:
            self._remove_admin_access(claims)
            record_event("denied")
            LOGGER.warning(
                "Django Admin OIDC access denied",
                extra={
                    "reason": "missing_required_claim_or_role",
                    "oidc_subject": claims.get("sub", ""),
                },
            )
        return verified

    def filter_users_by_claims(self, claims):
        email = claims.get("email")
        if not email:
            return self.UserModel.objects.none()
        return self.UserModel.objects.filter(email__iexact=email)

    def create_user(self, claims):
        email = claims["email"]
        user = self.UserModel.objects.create_user(**{self.UserModel.USERNAME_FIELD: email})
        user.set_unusable_password()
        return self._grant_admin_access(user, claims)

    def update_user(self, user, claims):
        return self._grant_admin_access(user, claims)

    def _grant_admin_access(self, user, claims):
        user.email = claims["email"]
        user.is_active = True
        if self._has_concrete_field("is_staff"):
            user.is_staff = True
        user.is_superuser = True
        user.set_unusable_password()
        user.save()
        self.request.session["admin_oidc_subject"] = claims["sub"]
        self.request.session["admin_oidc_authorized_at"] = int(time.time())
        record_event("success")
        LOGGER.info("Django Admin OIDC login succeeded", extra={"oidc_subject": claims["sub"]})
        return user

    def _remove_admin_access(self, claims):
        email = claims.get("email")
        if not email:
            return
        for user in self.UserModel.objects.filter(email__iexact=email):
            if self._has_concrete_field("is_staff"):
                user.is_staff = False
            user.is_superuser = False
            user.save()

    def _has_concrete_field(self, name):
        return any(field.name == name for field in self.UserModel._meta.concrete_fields)
