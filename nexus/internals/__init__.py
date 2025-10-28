import logging
from abc import ABC

import requests
from django.conf import settings

from nexus.cache import TokenCache

logger = logging.getLogger(__name__)


class InternalAuthenticationTokenError(Exception):
    pass


class InternalAuthentication:
    """
    Internal authentication client with simple token cache.
    """

    def __init__(self):
        self.token_cache = TokenCache(cache_key_prefix="keycloak_internal")

    def _fetch_token_from_keycloak(self) -> str:
        """Fetch new token from Keycloak."""
        logger.debug("Fetching new token from Keycloak")

        try:
            response = requests.post(
                url=settings.OIDC_OP_TOKEN_ENDPOINT,
                data={
                    "client_id": settings.OIDC_RP_CLIENT_ID,
                    "client_secret": settings.OIDC_RP_CLIENT_SECRET,
                    "grant_type": "client_credentials",
                },
                timeout=30,
            )
            response.raise_for_status()

            token = response.json().get("access_token")

            if token:
                return f"Bearer {token}"

            raise InternalAuthenticationTokenError("Access token not found in response")

        except requests.exceptions.RequestException as e:
            logger.error(f"Failed to fetch Keycloak token: {e}")
            raise InternalAuthenticationTokenError(f"Failed to fetch token: {e}") from e

    def _get_module_token(self):
        """Get token using cache."""
        try:
            return self.token_cache.get_or_generate(identifier="main", token_factory=self._fetch_token_from_keycloak)
        except Exception as e:
            logger.error(f"Error getting token: {e}")
            raise InternalAuthenticationTokenError(f"Token retrieval failed: {e}") from e

    def invalidate_cache(self):
        """Invalidate token cache - useful for retry in case of 401/403."""
        self.token_cache.invalidate("main")

    @property
    def headers(self):
        return {
            "Content-Type": "application/json; charset: utf-8",
            "Authorization": self._get_module_token(),
        }

    def make_request_with_retry(self, method: str, url: str, **kwargs):
        """
        Make request with automatic retry in case of auth error.
        """
        headers = kwargs.pop("headers", {})
        headers.update(self.headers)

        response = requests.request(method, url, headers=headers, **kwargs)

        if response.status_code in (401, 403):
            logger.warning(f"Auth error (HTTP {response.status_code}), retrying with fresh token")
            self.invalidate_cache()

            headers.update(self.headers)
            response = requests.request(method, url, headers=headers, **kwargs)

        return response


class RestClient(ABC):
    pass
