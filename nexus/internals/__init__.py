import requests
from django.conf import settings
from abc import ABC

class InternalAuthenticationTokenError:
    pass


class InternalAuthentication:
    def _get_module_token(self):
        request = requests.post(
            url=settings.OIDC_OP_TOKEN_ENDPOINT,
            data={
                "client_id": settings.OIDC_RP_CLIENT_ID,
                "client_secret": settings.OIDC_RP_CLIENT_SECRET,
                "grant_type": "client_credentials",
            },
        )
        token = request.json().get("access_token")
        if token:
            return f"Bearer {token}"
        raise InternalAuthenticationTokenError("Token is None")

    @property
    def headers(self):
        return {
            "Content-Type": "application/json; charset: utf-8",
            "Authorization": self._get_module_token(),
        }


class RestClient(ABC):
    pass