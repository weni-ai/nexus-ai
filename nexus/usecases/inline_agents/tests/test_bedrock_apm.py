from io import BytesIO
from unittest.mock import Mock, patch

from django.test import TestCase, override_settings

from nexus.usecases.inline_agents.bedrock import BedrockClient


class TestBedrockClientElasticAPM(TestCase):
    def setUp(self):
        self.client = BedrockClient()
        self.lambda_name = "test-lambda-function"
        self.lambda_role = "arn:aws:iam::123456789012:role/test-role"
        self.skill_handler = "lambda_function.lambda_handler"
        self.zip_buffer = BytesIO(b"mock zip content")

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=False,
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    def test_create_lambda_function_with_apm_disabled(self):
        """Tests that when APM is disabled, it does not add layers or environment variables"""
        mock_lambda_client = Mock()
        mock_lambda_client.create_function.return_value = {
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function"
        }
        self.client.lambda_client = mock_lambda_client

        self.client.create_lambda_function(
            lambda_name=self.lambda_name,
            lambda_role=self.lambda_role,
            skill_handler=self.skill_handler,
            zip_buffer=self.zip_buffer,
        )

        # Verify that create_function was called
        mock_lambda_client.create_function.assert_called_once()

        # Verify that Layers was not passed in parameters
        call_args = mock_lambda_client.create_function.call_args
        self.assertNotIn("Layers", call_args.kwargs)

        # Verify that Environment was not passed in parameters
        self.assertNotIn("Environment", call_args.kwargs)

        # Verify that basic parameters are present
        self.assertEqual(call_args.kwargs["FunctionName"], self.lambda_name)
        self.assertEqual(call_args.kwargs["Runtime"], "python3.12")
        self.assertEqual(call_args.kwargs["Role"], self.lambda_role)
        self.assertEqual(call_args.kwargs["Handler"], self.skill_handler)

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=True,
        ELASTIC_APM_LAMBDA_APM_SERVER="https://apm-server.example.com",
        ELASTIC_APM_LAMBDA_SECRET_TOKEN="test-secret-token",
        ELASTIC_APM_LAMBDA_ARCHITECTURE="x86_64",
        ELASTIC_APM_LAMBDA_EXTENSION_VERSION="1-6-0",
        ELASTIC_APM_LAMBDA_PYTHON_AGENT_VERSION="6-25-0",
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    def test_create_lambda_function_with_apm_enabled(self):
        """Tests that when APM is enabled, it adds layers and environment variables correctly"""
        mock_lambda_client = Mock()
        mock_lambda_client.create_function.return_value = {
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function"
        }
        self.client.lambda_client = mock_lambda_client

        self.client.create_lambda_function(
            lambda_name=self.lambda_name,
            lambda_role=self.lambda_role,
            skill_handler=self.skill_handler,
            zip_buffer=self.zip_buffer,
        )

        # Verify that create_function was called
        mock_lambda_client.create_function.assert_called_once()

        # Verify the parameters passed
        call_args = mock_lambda_client.create_function.call_args
        call_kwargs = call_args.kwargs

        # Verify that Layers was added
        self.assertIn("Layers", call_kwargs)
        layers = call_kwargs["Layers"]
        self.assertEqual(len(layers), 2)

        # Verify the layer ARNs
        expected_extension_layer = (
            "arn:aws:lambda:us-east-1:267093732750:layer:elastic-apm-extension-ver-1-6-0-x86_64:1"
        )
        expected_python_agent_layer = "arn:aws:lambda:us-east-1:267093732750:layer:elastic-apm-python-ver-6-25-0:1"
        self.assertIn(expected_extension_layer, layers)
        self.assertIn(expected_python_agent_layer, layers)

        # Verify that Environment was added
        self.assertIn("Environment", call_kwargs)
        environment = call_kwargs["Environment"]
        self.assertIn("Variables", environment)

        # Verify the environment variables
        env_vars = environment["Variables"]
        self.assertEqual(env_vars["AWS_LAMBDA_EXEC_WRAPPER"], "/opt/python/bin/elasticapm-lambda")
        self.assertEqual(env_vars["ELASTIC_APM_LAMBDA_APM_SERVER"], "https://apm-server.example.com")
        self.assertEqual(env_vars["ELASTIC_APM_SECRET_TOKEN"], "test-secret-token")
        self.assertEqual(env_vars["ELASTIC_APM_SEND_STRATEGY"], "background")

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=True,
        ELASTIC_APM_LAMBDA_APM_SERVER="",
        ELASTIC_APM_LAMBDA_SECRET_TOKEN="test-secret-token",
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    def test_create_lambda_function_with_apm_enabled_but_missing_server_url(self):
        """Tests that when APM is enabled but server URL is missing, it does not add environment variables"""
        mock_lambda_client = Mock()
        mock_lambda_client.create_function.return_value = {
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function"
        }
        self.client.lambda_client = mock_lambda_client

        self.client.create_lambda_function(
            lambda_name=self.lambda_name,
            lambda_role=self.lambda_role,
            skill_handler=self.skill_handler,
            zip_buffer=self.zip_buffer,
        )

        call_args = mock_lambda_client.create_function.call_args
        call_kwargs = call_args.kwargs

        # Verify that Environment was not added when configuration is missing
        self.assertNotIn("Environment", call_kwargs)

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=True,
        ELASTIC_APM_LAMBDA_APM_SERVER="https://apm-server.example.com",
        ELASTIC_APM_LAMBDA_SECRET_TOKEN="",
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    def test_create_lambda_function_with_apm_enabled_but_missing_secret_token(self):
        """Tests that when APM is enabled but secret token is missing, it does not add environment variables"""
        mock_lambda_client = Mock()
        mock_lambda_client.create_function.return_value = {
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function"
        }
        self.client.lambda_client = mock_lambda_client

        self.client.create_lambda_function(
            lambda_name=self.lambda_name,
            lambda_role=self.lambda_role,
            skill_handler=self.skill_handler,
            zip_buffer=self.zip_buffer,
        )

        call_args = mock_lambda_client.create_function.call_args
        call_kwargs = call_args.kwargs

        # Verify that Environment was not added when configuration is missing
        self.assertNotIn("Environment", call_kwargs)

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=True,
        ELASTIC_APM_LAMBDA_APM_SERVER="https://apm-server.example.com",
        ELASTIC_APM_LAMBDA_SECRET_TOKEN="test-secret-token",
        ELASTIC_APM_LAMBDA_ARCHITECTURE="arm64",
        ELASTIC_APM_LAMBDA_EXTENSION_VERSION="1-6-0",
        ELASTIC_APM_LAMBDA_PYTHON_AGENT_VERSION="6-25-0",
        AWS_BEDROCK_REGION_NAME="us-west-2",
    )
    def test_create_lambda_function_with_arm64_architecture(self):
        """Tests that arm64 architecture is used correctly in layer ARNs"""
        mock_lambda_client = Mock()
        mock_lambda_client.create_function.return_value = {
            "FunctionArn": "arn:aws:lambda:us-west-2:123456789012:function:test-lambda-function"
        }
        self.client.lambda_client = mock_lambda_client

        self.client.create_lambda_function(
            lambda_name=self.lambda_name,
            lambda_role=self.lambda_role,
            skill_handler=self.skill_handler,
            zip_buffer=self.zip_buffer,
        )

        call_args = mock_lambda_client.create_function.call_args
        call_kwargs = call_args.kwargs

        # Verify that Layers was added
        self.assertIn("Layers", call_kwargs)
        layers = call_kwargs["Layers"]

        # Verify the extension layer ARN with arm64
        expected_extension_layer = "arn:aws:lambda:us-west-2:267093732750:layer:elastic-apm-extension-ver-1-6-0-arm64:1"
        self.assertIn(expected_extension_layer, layers)

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=False,
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    @patch.object(BedrockClient, "update_lambda_alias")
    def test_update_lambda_function_with_apm_disabled(self, mock_update_alias):
        """Tests that when APM is disabled, update does not add layers or variables"""
        mock_lambda_client = Mock()
        mock_lambda_client.update_function_code.return_value = {
            "Version": "1",
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function",
        }
        mock_lambda_client.get_waiter.return_value.wait = Mock()
        self.client.lambda_client = mock_lambda_client

        self.client.update_lambda_function(self.lambda_name, self.zip_buffer)

        # Verify that update_function_configuration was NOT called
        mock_lambda_client.update_function_configuration.assert_not_called()
        # Verify that update_lambda_alias was called
        mock_update_alias.assert_called_once_with(self.lambda_name, "1")

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=True,
        ELASTIC_APM_LAMBDA_APM_SERVER="https://apm-server.example.com",
        ELASTIC_APM_LAMBDA_SECRET_TOKEN="test-secret-token",
        ELASTIC_APM_LAMBDA_ARCHITECTURE="x86_64",
        ELASTIC_APM_LAMBDA_EXTENSION_VERSION="1-6-0",
        ELASTIC_APM_LAMBDA_PYTHON_AGENT_VERSION="6-25-0",
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    @patch.object(BedrockClient, "update_lambda_alias")
    def test_update_lambda_function_with_apm_enabled_merges_environment_variables(self, mock_update_alias):
        """Tests that update merges existing environment variables with APM variables"""
        mock_lambda_client = Mock()
        mock_lambda_client.update_function_code.return_value = {
            "Version": "2",
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function",
        }
        mock_lambda_client.get_waiter.return_value.wait = Mock()
        mock_lambda_client.get_function_configuration.return_value = {
            "Environment": {"Variables": {"EXISTING_VAR": "existing_value", "ANOTHER_VAR": "another_value"}}
        }
        self.client.lambda_client = mock_lambda_client

        self.client.update_lambda_function(self.lambda_name, self.zip_buffer)

        # Verify that update_function_configuration was called
        mock_lambda_client.update_function_configuration.assert_called_once()

        # Verify the parameters passed
        call_args = mock_lambda_client.update_function_configuration.call_args
        call_kwargs = call_args.kwargs

        # Verify that Layers was added
        self.assertIn("Layers", call_kwargs)
        layers = call_kwargs["Layers"]
        self.assertEqual(len(layers), 2)

        # Verify that Environment was added with merged variables
        self.assertIn("Environment", call_kwargs)
        environment = call_kwargs["Environment"]
        env_vars = environment["Variables"]

        # Verify that existing variables were preserved
        self.assertEqual(env_vars["EXISTING_VAR"], "existing_value")
        self.assertEqual(env_vars["ANOTHER_VAR"], "another_value")

        # Verify that APM variables were added
        self.assertEqual(env_vars["AWS_LAMBDA_EXEC_WRAPPER"], "/opt/python/bin/elasticapm-lambda")
        self.assertEqual(env_vars["ELASTIC_APM_LAMBDA_APM_SERVER"], "https://apm-server.example.com")
        self.assertEqual(env_vars["ELASTIC_APM_SECRET_TOKEN"], "test-secret-token")
        self.assertEqual(env_vars["ELASTIC_APM_SEND_STRATEGY"], "background")

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=True,
        ELASTIC_APM_LAMBDA_APM_SERVER="https://apm-server.example.com",
        ELASTIC_APM_LAMBDA_SECRET_TOKEN="test-secret-token",
        ELASTIC_APM_LAMBDA_ARCHITECTURE="x86_64",
        ELASTIC_APM_LAMBDA_EXTENSION_VERSION="1-6-0",
        ELASTIC_APM_LAMBDA_PYTHON_AGENT_VERSION="6-25-0",
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    @patch.object(BedrockClient, "update_lambda_alias")
    def test_update_lambda_function_with_apm_enabled_no_existing_environment(self, mock_update_alias):
        """Tests that update works even when there are no existing environment variables"""
        mock_lambda_client = Mock()
        mock_lambda_client.update_function_code.return_value = {
            "Version": "2",
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function",
        }
        mock_lambda_client.get_waiter.return_value.wait = Mock()
        mock_lambda_client.get_function_configuration.return_value = {
            "Environment": {"Variables": {}}  # No existing environment variables
        }
        self.client.lambda_client = mock_lambda_client

        self.client.update_lambda_function(self.lambda_name, self.zip_buffer)

        # Verify that update_function_configuration was called
        mock_lambda_client.update_function_configuration.assert_called_once()

        # Verify the parameters passed
        call_args = mock_lambda_client.update_function_configuration.call_args
        call_kwargs = call_args.kwargs

        # Verify that Environment was added only with APM variables
        self.assertIn("Environment", call_kwargs)
        environment = call_kwargs["Environment"]
        env_vars = environment["Variables"]

        # Verify that only APM variables are present
        self.assertEqual(len(env_vars), 4)
        self.assertEqual(env_vars["AWS_LAMBDA_EXEC_WRAPPER"], "/opt/python/bin/elasticapm-lambda")
        self.assertEqual(env_vars["ELASTIC_APM_LAMBDA_APM_SERVER"], "https://apm-server.example.com")
        self.assertEqual(env_vars["ELASTIC_APM_SECRET_TOKEN"], "test-secret-token")
        self.assertEqual(env_vars["ELASTIC_APM_SEND_STRATEGY"], "background")

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=True,
        ELASTIC_APM_LAMBDA_APM_SERVER="https://apm-server.example.com",
        ELASTIC_APM_LAMBDA_SECRET_TOKEN="test-secret-token",
        ELASTIC_APM_LAMBDA_ARCHITECTURE="x86_64",
        ELASTIC_APM_LAMBDA_EXTENSION_VERSION="1-6-0",
        ELASTIC_APM_LAMBDA_PYTHON_AGENT_VERSION="6-25-0",
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    @patch.object(BedrockClient, "update_lambda_alias")
    def test_update_lambda_function_with_apm_enabled_handles_exception(self, mock_update_alias):
        """Tests that update handles exceptions when getting current configuration"""
        mock_lambda_client = Mock()
        mock_lambda_client.update_function_code.return_value = {
            "Version": "2",
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function",
        }
        mock_lambda_client.get_waiter.return_value.wait = Mock()
        mock_lambda_client.get_function_configuration.side_effect = Exception("Config error")
        self.client.lambda_client = mock_lambda_client

        self.client.update_lambda_function(self.lambda_name, self.zip_buffer)

        # Verify that update_function_configuration was called even with error
        mock_lambda_client.update_function_configuration.assert_called_once()

        # Verify that only APM variables were used (fallback)
        call_args = mock_lambda_client.update_function_configuration.call_args
        call_kwargs = call_args.kwargs
        env_vars = call_kwargs["Environment"]["Variables"]

        # Verify that only APM variables are present
        self.assertEqual(len(env_vars), 4)
        self.assertEqual(env_vars["AWS_LAMBDA_EXEC_WRAPPER"], "/opt/python/bin/elasticapm-lambda")
