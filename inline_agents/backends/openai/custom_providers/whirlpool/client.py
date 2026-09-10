"""Whirlpool OAuth2 + generateContent HTTP client."""

from __future__ import annotations

import base64
import logging
import os
import time
from typing import Any, Dict, Optional, Tuple

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TOKEN_URL = "https://api-dev.whirlpool.com/oauth2/v1/token"
DEFAULT_GENERATE_CONTENT_URL = "https://api-dev.whirlpool.com/d2c/cxplatform/v1/ai/generateContent"

# In-process token cache: key -> (access_token, expires_at_monotonic)
_token_cache: Dict[str, Tuple[str, float]] = {}
_TOKEN_SKEW_SECONDS = 60.0


class WhirlpoolAPIError(Exception):
    """Raised when Whirlpool auth or generateContent fails."""

    def __init__(self, message: str, *, status_code: int | None = None, body: Any = None):
        super().__init__(message)
        self.status_code = status_code
        self.body = body


class WhirlpoolClient:
    def __init__(self, credentials: Dict[str, Any] | None = None):
        creds = credentials or {}
        self.client_id = (
            creds.get("client_id") or os.getenv("WHIRLPOOL_CLIENT_ID") or ""
        ).strip()
        self.client_secret = (
            creds.get("client_secret") or os.getenv("WHIRLPOOL_CLIENT_SECRET") or ""
        ).strip()

        api_base = (creds.get("api_base") or "").rstrip("/")
        token_url = (creds.get("token_url") or "").strip()
        generate_url = (creds.get("generate_content_url") or "").strip()

        if token_url:
            self.token_url = token_url
        elif api_base:
            self.token_url = f"{api_base}/oauth2/v1/token"
        else:
            self.token_url = DEFAULT_TOKEN_URL

        if generate_url:
            self.generate_content_url = generate_url
        elif api_base:
            self.generate_content_url = f"{api_base}/d2c/cxplatform/v1/ai/generateContent"
        else:
            self.generate_content_url = DEFAULT_GENERATE_CONTENT_URL

        if not self.client_id or not self.client_secret:
            raise WhirlpoolAPIError(
                "Whirlpool credentials missing: set ProjectModelProvider "
                "client_id/client_secret or WHIRLPOOL_CLIENT_ID / WHIRLPOOL_CLIENT_SECRET"
            )

    def _cache_key(self) -> str:
        return f"{self.client_id}:{self.token_url}"

    async def get_access_token(self, *, force_refresh: bool = False) -> str:
        key = self._cache_key()
        if not force_refresh:
            cached = _token_cache.get(key)
            if cached and cached[1] > time.monotonic():
                return cached[0]

        basic = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        headers = {
            "Authorization": f"Basic {basic}",
            "Content-Type": "application/x-www-form-urlencoded",
        }
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(
                self.token_url,
                headers=headers,
                data={"grant_type": "client_credentials"},
            )

        if response.status_code >= 400:
            raise WhirlpoolAPIError(
                f"Whirlpool OAuth token request failed with status {response.status_code}",
                status_code=response.status_code,
                body=_safe_json(response),
            )

        payload = response.json()
        token = payload.get("access_token")
        if not token:
            raise WhirlpoolAPIError("Whirlpool OAuth response missing access_token", body=payload)

        expires_in = float(payload.get("expires_in") or 3600)
        _token_cache[key] = (token, time.monotonic() + max(expires_in - _TOKEN_SKEW_SECONDS, 30.0))
        return token

    async def generate_content(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        token = await self.get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        async with httpx.AsyncClient(timeout=120.0) as client:
            response = await client.post(
                self.generate_content_url,
                headers=headers,
                json=payload,
            )

            # Retry once on auth failure with a fresh token
            if response.status_code in (401, 403):
                logger.warning("Whirlpool generateContent auth failed; refreshing token")
                token = await self.get_access_token(force_refresh=True)
                headers["Authorization"] = f"Bearer {token}"
                response = await client.post(
                    self.generate_content_url,
                    headers=headers,
                    json=payload,
                )

        body = _safe_json(response)
        if response.status_code >= 400:
            raise WhirlpoolAPIError(
                f"Whirlpool generateContent failed with status {response.status_code}: {body}",
                status_code=response.status_code,
                body=body,
            )
        if not isinstance(body, dict):
            raise WhirlpoolAPIError("Whirlpool generateContent returned non-object JSON", body=body)
        return body


def clear_token_cache() -> None:
    """Test helper to reset the in-process OAuth cache."""
    _token_cache.clear()


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except Exception:
        return response.text
