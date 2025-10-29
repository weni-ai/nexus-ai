import logging
from urllib.error import HTTPError as UrllibHTTPError
from urllib.parse import parse_qs

import jwt
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.conf import settings
from django.contrib.auth.models import AnonymousUser
from mozilla_django_oidc.auth import OIDCAuthenticationBackend
from requests.exceptions import HTTPError as RequestsHTTPError
from rest_framework import authentication
from rest_framework.exceptions import AuthenticationFailed

from nexus.orgs import permissions
from nexus.usecases.users import CreateUserUseCase

LOGGER = logging.getLogger("weni_django_oidc")


class WeniOIDCAuthenticationBackend(OIDCAuthenticationBackend):
    def verify_claims(self, claims):
        verified = super().verify_claims(claims)
        return verified

    def get_username(self, claims):
        username = claims.get("preferred_username")
        if username:
            return username
        return super().get_username(claims=claims)

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
        authorization_header = request.headers.get("Authorization")

        if not authorization_header:
            return None

        is_super_user = permissions.is_super_user(authorization_header)

        if not is_super_user:
            return None

        return (is_super_user, None)


@database_sync_to_async
def get_keycloak_user(token_key):
    auth = WeniOIDCAuthenticationBackend()
    return auth.get_or_create_user(token_key, None, None)


class TokenAuthMiddleware(BaseMiddleware):
    def __init__(self, inner):
        super().__init__(inner)

    async def __call__(self, scope, receive, send):
        try:
            query_params = parse_qs(scope["query_string"].decode())
            scope["query_params"] = query_params
            token_key = query_params.get("Token")[0]
        except (ValueError, TypeError):
            token_key = None
        try:
            user = await get_keycloak_user(token_key)
        except (UrllibHTTPError, RequestsHTTPError):
            user = None
            LOGGER.debug("Keycloak Websocket Login failed")

        scope["user"] = AnonymousUser() if user is None else user
        return await super().__call__(scope, receive, send)


class JWTAuthentication(authentication.BaseAuthentication):
    def authenticate(self, request):
        public_key = settings.JWT_PUBLIC_KEY

        if not public_key:
            raise AuthenticationFailed("JWT public key is not set, please set the JWT_PUBLIC_KEY environment variable")

        auth_header = request.headers.get("Authorization", "")

        if not isinstance(auth_header, str) or not auth_header.startswith("Bearer "):
            raise AuthenticationFailed("Missing or invalid Authorization header.")

        token = auth_header.split(" ")[1]

        try:
            payload = jwt.decode(token, public_key, algorithms=["RS256"], options={"verify_aud": False})
        except jwt.ExpiredSignatureError as e:
            raise AuthenticationFailed("Token has expired") from e
        except jwt.InvalidTokenError as e:
            raise AuthenticationFailed("Invalid token") from e
        project_uuid = payload.get("project_uuid")
        if not project_uuid:
            raise AuthenticationFailed("Project UUID is required")

        request.project_uuid = project_uuid
        request.jwt_payload = payload

        return (None, None)
