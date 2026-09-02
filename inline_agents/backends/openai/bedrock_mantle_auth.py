"""Short-lived Bedrock bearer tokens from the process AWS credential chain.

Matches aws-bedrock-token-generator: SigV4-presign CallWithBearerToken, then
base64-encode the URL. Used so aws_mantle can auth without a stored api_key.
"""

import base64
import logging
from typing import Optional
from urllib.parse import urlparse

import boto3
from botocore.auth import SigV4QueryAuth
from botocore.awsrequest import AWSRequest
from botocore.credentials import Credentials

logger = logging.getLogger(__name__)

_DEFAULT_HOST = "bedrock.amazonaws.com"
_SERVICE_NAME = "bedrock"
_AUTH_PREFIX = "bedrock-api-key-"
_TOKEN_VERSION = "&Version=1"
_TOKEN_DURATION_SECONDS = 43200


class BedrockMantleAuthError(RuntimeError):
    """Raised when the pod credential chain cannot mint a Mantle bearer token."""


def mint_bedrock_bearer_token(
    *,
    region: Optional[str] = None,
    credentials: Optional[Credentials] = None,
) -> str:
    """Mint a short-lived Bedrock API key from IAM credentials.

    The token is valid up to 12 hours, or until the underlying credentials expire.
    Do not log the return value.
    """
    resolved_region = region or "us-west-2"
    signing_credentials = credentials or _load_process_credentials()

    request = AWSRequest(
        method="POST",
        url=f"https://{_DEFAULT_HOST}/",
        headers={"host": _DEFAULT_HOST},
        params={"Action": "CallWithBearerToken"},
    )
    auth = SigV4QueryAuth(
        signing_credentials,
        _SERVICE_NAME,
        resolved_region,
        expires=_TOKEN_DURATION_SECONDS,
    )
    auth.add_auth(request)

    presigned_url = request.url.replace("https://", "") + _TOKEN_VERSION
    encoded_token = base64.b64encode(presigned_url.encode("utf-8")).decode("utf-8")
    return f"{_AUTH_PREFIX}{encoded_token}"


def region_from_mantle_base(base_url: str) -> str:
    """Read the region from a bedrock-mantle host; default to us-west-2."""
    host = urlparse(base_url).hostname or ""
    parts = host.split(".")
    if len(parts) >= 2 and parts[0] == "bedrock-mantle":
        return parts[1]
    return "us-west-2"


def resolve_aws_mantle_api_key(explicit_key: str, *, region: Optional[str] = None) -> str:
    """Prefer a stored Bedrock key; otherwise mint from the pod IAM role."""
    if explicit_key:
        return explicit_key
    logger.info("Minting short-lived Bedrock token from the process credential chain")
    return mint_bedrock_bearer_token(region=region or "us-west-2")


def _load_process_credentials() -> Credentials:
    session_credentials = boto3.Session().get_credentials()
    if session_credentials is None:
        raise BedrockMantleAuthError(
            "No AWS credentials in the process chain for aws_mantle. "
            "The pod IAM role (or local default chain) must be able to call Bedrock."
        )
    frozen = session_credentials.get_frozen_credentials()
    return Credentials(frozen.access_key, frozen.secret_key, frozen.token)
