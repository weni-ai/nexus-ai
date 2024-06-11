import logging
from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from nexus.usecases.users import CreateUserUseCase

from rest_framework import authentication
from rest_framework import exceptions

from nexus.orgs import permissions


LOGGER = logging.getLogger("weni_django_oidc")


class WeniOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    def verify_claims(self, claims):
        verified = super(WeniOIDCAuthenticationBackend, self).verify_claims(claims)
        return verified

    def get_username(self, claims):
        username = claims.get("preferred_username")
        if username:
            return username
        return super(WeniOIDCAuthenticationBackend, self).get_username(claims=claims)

    def create_user(self, claims):
        # Override existing create_user method in OIDCAuthenticationBackend
        email = claims.get("email")
        return CreateUserUseCase().create_user(email)

    def update_user(self, user, claims):
        user.name = claims.get("name", "")
        user.email = claims.get("email", "")
        user.save()

        return user


class ExternalTokenAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        authorization_header = request.headers.get('Authorization')

        if not authorization_header:
            return None

        is_super_user = permissions.is_super_user(authorization_header)

        if not is_super_user:
            raise exceptions.AuthenticationFailed('Invalid Token')

        return (is_super_user, None)
