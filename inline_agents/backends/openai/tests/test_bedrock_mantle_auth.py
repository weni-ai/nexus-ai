import base64
from unittest.mock import MagicMock, patch

from botocore.credentials import Credentials
from django.test import SimpleTestCase

from inline_agents.backends.openai.bedrock_mantle_auth import (
    BedrockMantleAuthError,
    mint_bedrock_bearer_token,
    region_from_mantle_base,
    resolve_aws_mantle_api_key,
)


class MintBedrockBearerTokenTests(SimpleTestCase):
    def test_token_is_presigned_call_with_bearer_token(self):
        credentials = Credentials("AKIATEST", "secret", "session-token")

        token = mint_bedrock_bearer_token(region="us-west-2", credentials=credentials)

        self.assertTrue(token.startswith("bedrock-api-key-"))
        payload = base64.b64decode(token.removeprefix("bedrock-api-key-")).decode("utf-8")
        self.assertTrue(payload.startswith("bedrock.amazonaws.com/"))
        self.assertIn("Action=CallWithBearerToken", payload)
        self.assertTrue(payload.endswith("&Version=1"))
        self.assertIn("X-Amz-Algorithm=AWS4-HMAC-SHA256", payload)
        self.assertIn("X-Amz-Security-Token=session-token", payload)

    def test_loads_process_credentials_when_none_passed(self):
        frozen = MagicMock()
        frozen.access_key = "AKIAPROCESS"
        frozen.secret_key = "process-secret"
        frozen.token = None
        session_credentials = MagicMock()
        session_credentials.get_frozen_credentials.return_value = frozen
        session = MagicMock()
        session.get_credentials.return_value = session_credentials

        with patch(
            "inline_agents.backends.openai.bedrock_mantle_auth.boto3.Session",
            return_value=session,
        ):
            token = mint_bedrock_bearer_token(region="us-west-2")

        self.assertTrue(token.startswith("bedrock-api-key-"))
        payload = base64.b64decode(token.removeprefix("bedrock-api-key-")).decode("utf-8")
        self.assertIn("AKIAPROCESS", payload)

    def test_raises_when_process_chain_is_empty(self):
        session = MagicMock()
        session.get_credentials.return_value = None

        with patch(
            "inline_agents.backends.openai.bedrock_mantle_auth.boto3.Session",
            return_value=session,
        ):
            with self.assertRaises(BedrockMantleAuthError):
                mint_bedrock_bearer_token(region="us-west-2")


class ResolveAwsMantleApiKeyTests(SimpleTestCase):
    def test_stored_key_wins(self):
        with patch(
            "inline_agents.backends.openai.bedrock_mantle_auth.mint_bedrock_bearer_token"
        ) as mint:
            self.assertEqual(resolve_aws_mantle_api_key("project-key"), "project-key")
            mint.assert_not_called()

    def test_empty_key_mints_from_pod_chain(self):
        with patch(
            "inline_agents.backends.openai.bedrock_mantle_auth.mint_bedrock_bearer_token",
            return_value="bedrock-api-key-minted",
        ) as mint:
            self.assertEqual(resolve_aws_mantle_api_key(""), "bedrock-api-key-minted")
            mint.assert_called_once_with(region="us-west-2")

    def test_empty_key_forwards_explicit_region(self):
        with patch(
            "inline_agents.backends.openai.bedrock_mantle_auth.mint_bedrock_bearer_token",
            return_value="bedrock-api-key-minted",
        ) as mint:
            resolve_aws_mantle_api_key("", region="us-east-1")
            mint.assert_called_once_with(region="us-east-1")


class RegionFromMantleBaseTests(SimpleTestCase):
    def test_reads_region_from_host(self):
        self.assertEqual(
            region_from_mantle_base("https://bedrock-mantle.us-east-1.api.aws/openai/v1"),
            "us-east-1",
        )

    def test_defaults_when_host_is_unknown(self):
        self.assertEqual(region_from_mantle_base(""), "us-west-2")
