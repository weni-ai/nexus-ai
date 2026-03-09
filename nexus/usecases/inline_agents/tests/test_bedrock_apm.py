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
        AWS_LAMBDA_ARCHITECTURE="arm64",
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
        # Verify that Architectures is always set (default is arm64)
        self.assertIn("Architectures", call_args.kwargs)
        self.assertEqual(call_args.kwargs["Architectures"], ["arm64"])

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=True,
        ELASTIC_APM_LAMBDA_APM_SERVER="https://apm-server.example.com",
        ELASTIC_APM_LAMBDA_SECRET_TOKEN="test-secret-token",
        AWS_LAMBDA_ARCHITECTURE="x86_64",
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

        # Verify that Architectures was added
        self.assertIn("Architectures", call_kwargs)
        self.assertEqual(call_kwargs["Architectures"], ["x86_64"])

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
        # ELASTIC_APM_ENVIRONMENT is always present (default is empty string)
        self.assertIn("ELASTIC_APM_ENVIRONMENT", env_vars)
        self.assertEqual(env_vars["ELASTIC_APM_ENVIRONMENT"], "")

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=True,
        ELASTIC_APM_LAMBDA_APM_SERVER="https://apm-server.example.com",
        ELASTIC_APM_LAMBDA_SECRET_TOKEN="test-secret-token",
        ELASTIC_APM_ENVIRONMENT="staging",
        AWS_LAMBDA_ARCHITECTURE="x86_64",
        ELASTIC_APM_LAMBDA_EXTENSION_VERSION="1-6-0",
        ELASTIC_APM_LAMBDA_PYTHON_AGENT_VERSION="6-25-0",
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    def test_create_lambda_function_with_apm_environment_variable(self):
        """Tests that ELASTIC_APM_ENVIRONMENT is added when configured"""
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

        # Verify that Environment was added
        self.assertIn("Environment", call_kwargs)
        environment = call_kwargs["Environment"]
        env_vars = environment["Variables"]

        # Verify that ELASTIC_APM_ENVIRONMENT is present
        self.assertIn("ELASTIC_APM_ENVIRONMENT", env_vars)
        self.assertEqual(env_vars["ELASTIC_APM_ENVIRONMENT"], "staging")

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
        AWS_LAMBDA_ARCHITECTURE="arm64",
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

        # Verify that Architectures was set to arm64
        self.assertIn("Architectures", call_kwargs)
        self.assertEqual(call_kwargs["Architectures"], ["arm64"])

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=False,
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    @patch.object(BedrockClient, "update_lambda_alias")
    def test_update_lambda_function_with_apm_disabled(self, mock_update_alias):
        """Tests that when APM is disabled and no APM was present, update does not add layers or variables"""
        mock_lambda_client = Mock()
        mock_lambda_client.update_function_code.return_value = {
            "Version": "1",
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function",
        }
        mock_lambda_client.get_waiter.return_value.wait = Mock()
        # No APM layers or variables present
        mock_lambda_client.get_function_configuration.return_value = {
            "Architectures": ["x86_64"],
            "Layers": [],
            "Environment": {"Variables": {"OTHER_VAR": "value"}},
        }
        self.client.lambda_client = mock_lambda_client

        self.client.update_lambda_function(self.lambda_name, self.zip_buffer)

        # Verify that update_function_configuration was NOT called (no APM to remove)
        mock_lambda_client.update_function_configuration.assert_not_called()
        # Verify that update_lambda_alias was called
        mock_update_alias.assert_called_once_with(self.lambda_name, "1")

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=False,
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    @patch.object(BedrockClient, "update_lambda_alias")
    def test_update_lambda_function_removes_apm_when_disabled(self, mock_update_alias):
        """Tests that when APM is disabled but was previously enabled, it removes APM layers and variables"""
        mock_lambda_client = Mock()
        mock_lambda_client.update_function_code.return_value = {
            "Version": "2",
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function",
        }
        mock_lambda_client.get_waiter.return_value.wait = Mock()
        # APM layers and variables are present
        apm_extension_layer = "arn:aws:lambda:us-east-1:267093732750:layer:elastic-apm-extension-ver-1-6-0-x86_64:1"
        apm_python_layer = "arn:aws:lambda:us-east-1:267093732750:layer:elastic-apm-python-ver-6-25-0:1"
        mock_lambda_client.get_function_configuration.return_value = {
            "Architectures": ["x86_64"],
            "Layers": [
                {"Arn": apm_extension_layer},
                {"Arn": apm_python_layer},
            ],
            "Environment": {
                "Variables": {
                    "OTHER_VAR": "value",
                    "AWS_LAMBDA_EXEC_WRAPPER": "/opt/python/bin/elasticapm-lambda",
                    "ELASTIC_APM_LAMBDA_APM_SERVER": "https://apm-server.example.com",
                    "ELASTIC_APM_SECRET_TOKEN": "old-token",
                    "ELASTIC_APM_SEND_STRATEGY": "background",
                    "ELASTIC_APM_ENVIRONMENT": "staging",
                }
            },
        }
        self.client.lambda_client = mock_lambda_client

        self.client.update_lambda_function(self.lambda_name, self.zip_buffer)

        # Verify that update_function_configuration was called to remove APM
        mock_lambda_client.update_function_configuration.assert_called_once()

        # Verify the parameters passed
        call_args = mock_lambda_client.update_function_configuration.call_args
        call_kwargs = call_args.kwargs

        # Verify that Layers was set to empty (no APM layers)
        self.assertIn("Layers", call_kwargs)
        self.assertEqual(call_kwargs["Layers"], [])

        # Verify that Environment was updated to remove APM variables
        self.assertIn("Environment", call_kwargs)
        environment = call_kwargs["Environment"]
        env_vars = environment["Variables"]

        # Verify that APM variables were removed
        self.assertNotIn("AWS_LAMBDA_EXEC_WRAPPER", env_vars)
        self.assertNotIn("ELASTIC_APM_LAMBDA_APM_SERVER", env_vars)
        self.assertNotIn("ELASTIC_APM_SECRET_TOKEN", env_vars)
        self.assertNotIn("ELASTIC_APM_SEND_STRATEGY", env_vars)
        self.assertNotIn("ELASTIC_APM_ENVIRONMENT", env_vars)

        # Verify that non-APM variables were preserved
        self.assertEqual(env_vars["OTHER_VAR"], "value")

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=False,
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    @patch.object(BedrockClient, "update_lambda_alias")
    def test_update_lambda_function_removes_only_apm_layers_when_other_layers_present(self, mock_update_alias):
        """Tests that when APM is disabled, only APM layers are removed while other layers are preserved"""
        mock_lambda_client = Mock()
        mock_lambda_client.update_function_code.return_value = {
            "Version": "2",
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function",
        }
        mock_lambda_client.get_waiter.return_value.wait = Mock()
        # APM layers and non-APM layers are present
        apm_extension_layer = "arn:aws:lambda:us-east-1:267093732750:layer:elastic-apm-extension-ver-1-6-0-x86_64:1"
        apm_python_layer = "arn:aws:lambda:us-east-1:267093732750:layer:elastic-apm-python-ver-6-25-0:1"
        other_layer = "arn:aws:lambda:us-east-1:123456789012:layer:other-layer:1"
        mock_lambda_client.get_function_configuration.return_value = {
            "Architectures": ["x86_64"],
            "Layers": [
                {"Arn": other_layer},
                {"Arn": apm_extension_layer},
                {"Arn": apm_python_layer},
            ],
            "Environment": {"Variables": {"OTHER_VAR": "value"}},
        }
        self.client.lambda_client = mock_lambda_client

        self.client.update_lambda_function(self.lambda_name, self.zip_buffer)

        # Verify that update_function_configuration was called to remove APM layers
        mock_lambda_client.update_function_configuration.assert_called_once()

        # Verify the parameters passed
        call_args = mock_lambda_client.update_function_configuration.call_args
        call_kwargs = call_args.kwargs

        # Verify that Layers contains only the non-APM layer
        self.assertIn("Layers", call_kwargs)
        layers = call_kwargs["Layers"]
        self.assertEqual(len(layers), 1)
        self.assertEqual(layers[0], other_layer)
        self.assertNotIn(apm_extension_layer, layers)
        self.assertNotIn(apm_python_layer, layers)

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=True,
        ELASTIC_APM_LAMBDA_APM_SERVER="https://apm-server.example.com",
        ELASTIC_APM_LAMBDA_SECRET_TOKEN="test-secret-token",
        AWS_LAMBDA_ARCHITECTURE="x86_64",
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
            "Architectures": ["x86_64"],
            "Layers": [],
            "Environment": {"Variables": {"EXISTING_VAR": "existing_value", "ANOTHER_VAR": "another_value"}},
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
        # ELASTIC_APM_ENVIRONMENT is always present
        self.assertIn("ELASTIC_APM_ENVIRONMENT", env_vars)

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=True,
        ELASTIC_APM_LAMBDA_APM_SERVER="https://apm-server.example.com",
        ELASTIC_APM_LAMBDA_SECRET_TOKEN="test-secret-token",
        AWS_LAMBDA_ARCHITECTURE="x86_64",
        ELASTIC_APM_LAMBDA_EXTENSION_VERSION="1-6-0",
        ELASTIC_APM_LAMBDA_PYTHON_AGENT_VERSION="6-25-0",
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    @patch.object(BedrockClient, "update_lambda_alias")
    def test_update_lambda_function_with_apm_enabled_preserves_non_apm_layers(self, mock_update_alias):
        """Tests that when APM is enabled, non-APM layers are preserved"""
        mock_lambda_client = Mock()
        mock_lambda_client.update_function_code.return_value = {
            "Version": "2",
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function",
        }
        mock_lambda_client.get_waiter.return_value.wait = Mock()
        other_layer = "arn:aws:lambda:us-east-1:123456789012:layer:other-layer:1"
        mock_lambda_client.get_function_configuration.return_value = {
            "Architectures": ["x86_64"],
            "Layers": [{"Arn": other_layer}],
            "Environment": {"Variables": {"OTHER_VAR": "value"}},
        }
        self.client.lambda_client = mock_lambda_client

        self.client.update_lambda_function(self.lambda_name, self.zip_buffer)

        # Verify that update_function_configuration was called
        mock_lambda_client.update_function_configuration.assert_called_once()

        # Verify the parameters passed
        call_args = mock_lambda_client.update_function_configuration.call_args
        call_kwargs = call_args.kwargs

        # Verify that Layers contains both APM layers and the non-APM layer
        self.assertIn("Layers", call_kwargs)
        layers = call_kwargs["Layers"]
        # Should have 2 APM layers + 1 non-APM layer = 3 total
        self.assertEqual(len(layers), 3)
        # Verify non-APM layer is preserved
        self.assertIn(other_layer, layers)

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=True,
        ELASTIC_APM_LAMBDA_APM_SERVER="https://apm-server.example.com",
        ELASTIC_APM_LAMBDA_SECRET_TOKEN="test-secret-token",
        AWS_LAMBDA_ARCHITECTURE="x86_64",
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
            "Architectures": ["x86_64"],
            "Environment": {"Variables": {}},  # No existing environment variables
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

        # Verify that only APM variables are present (5 variables including ELASTIC_APM_ENVIRONMENT)
        self.assertEqual(len(env_vars), 5)
        self.assertEqual(env_vars["AWS_LAMBDA_EXEC_WRAPPER"], "/opt/python/bin/elasticapm-lambda")
        self.assertEqual(env_vars["ELASTIC_APM_LAMBDA_APM_SERVER"], "https://apm-server.example.com")
        self.assertEqual(env_vars["ELASTIC_APM_SECRET_TOKEN"], "test-secret-token")
        self.assertEqual(env_vars["ELASTIC_APM_SEND_STRATEGY"], "background")
        # ELASTIC_APM_ENVIRONMENT is always present
        self.assertIn("ELASTIC_APM_ENVIRONMENT", env_vars)
        self.assertEqual(env_vars["ELASTIC_APM_ENVIRONMENT"], "")

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=True,
        ELASTIC_APM_LAMBDA_APM_SERVER="https://apm-server.example.com",
        ELASTIC_APM_LAMBDA_SECRET_TOKEN="test-secret-token",
        AWS_LAMBDA_ARCHITECTURE="x86_64",
        ELASTIC_APM_LAMBDA_EXTENSION_VERSION="1-6-0",
        ELASTIC_APM_LAMBDA_PYTHON_AGENT_VERSION="6-25-0",
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    @patch.object(BedrockClient, "update_lambda_alias")
    def test_update_lambda_function_uses_lambda_actual_architecture_for_layers(self, mock_update_alias):
        """Tests that update uses the Lambda's actual architecture for layer ARNs, not the setting"""
        mock_lambda_client = Mock()
        mock_lambda_client.update_function_code.return_value = {
            "Version": "2",
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function",
        }
        mock_lambda_client.get_waiter.return_value.wait = Mock()
        # Lambda is arm64 but settings say x86_64
        mock_lambda_client.get_function_configuration.return_value = {
            "Architectures": ["arm64"],
            "Layers": [],
            "Environment": {"Variables": {}},
        }
        self.client.lambda_client = mock_lambda_client

        self.client.update_lambda_function(self.lambda_name, self.zip_buffer)

        # Verify that update_function_configuration was called
        mock_lambda_client.update_function_configuration.assert_called_once()

        call_args = mock_lambda_client.update_function_configuration.call_args
        call_kwargs = call_args.kwargs

        # Verify that Layers uses arm64 (Lambda's actual architecture), not x86_64 (settings)
        self.assertIn("Layers", call_kwargs)
        layers = call_kwargs["Layers"]
        expected_extension_layer = "arn:aws:lambda:us-east-1:267093732750:layer:elastic-apm-extension-ver-1-6-0-arm64:1"
        expected_python_agent_layer = "arn:aws:lambda:us-east-1:267093732750:layer:elastic-apm-python-ver-6-25-0:1"
        self.assertIn(expected_extension_layer, layers)
        self.assertIn(expected_python_agent_layer, layers)

        # Ensure x86_64 layer is NOT present (should use actual Lambda architecture)
        x86_extension_layer = "arn:aws:lambda:us-east-1:267093732750:layer:elastic-apm-extension-ver-1-6-0-x86_64:1"
        self.assertNotIn(x86_extension_layer, layers)

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=True,
        ELASTIC_APM_LAMBDA_APM_SERVER="https://apm-server.example.com",
        ELASTIC_APM_LAMBDA_SECRET_TOKEN="test-secret-token",
        AWS_LAMBDA_ARCHITECTURE="x86_64",
        ELASTIC_APM_LAMBDA_EXTENSION_VERSION="1-6-0",
        ELASTIC_APM_LAMBDA_PYTHON_AGENT_VERSION="6-25-0",
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    @patch.object(BedrockClient, "update_lambda_alias")
    @patch("nexus.usecases.inline_agents.bedrock.logger")
    def test_update_lambda_function_with_apm_enabled_handles_exception(self, mock_logger, mock_update_alias):
        """Tests that update handles exceptions when getting current configuration and logs the error"""
        mock_lambda_client = Mock()
        mock_lambda_client.update_function_code.return_value = {
            "Version": "2",
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function",
        }
        mock_lambda_client.get_waiter.return_value.wait = Mock()
        config_error = Exception("Config error")
        mock_lambda_client.get_function_configuration.side_effect = config_error
        self.client.lambda_client = mock_lambda_client

        self.client.update_lambda_function(self.lambda_name, self.zip_buffer)

        # Verify that error was logged with proper context
        mock_logger.error.assert_called_once()
        error_call_args = mock_logger.error.call_args
        self.assertEqual(error_call_args.args[0], "Failed to get current Lambda function configuration")
        self.assertIn("lambda_name", error_call_args.kwargs["extra"])
        self.assertEqual(error_call_args.kwargs["extra"]["lambda_name"], self.lambda_name)
        self.assertIn("error_type", error_call_args.kwargs["extra"])
        self.assertIn("error_message", error_call_args.kwargs["extra"])
        self.assertTrue(error_call_args.kwargs["exc_info"])

        # Verify that update_function_configuration was called even with error
        mock_lambda_client.update_function_configuration.assert_called_once()

        # Verify that only APM variables were used (fallback)
        call_args = mock_lambda_client.update_function_configuration.call_args
        call_kwargs = call_args.kwargs
        env_vars = call_kwargs["Environment"]["Variables"]

        # Verify that only APM variables are present (5 variables including ELASTIC_APM_ENVIRONMENT)
        self.assertEqual(len(env_vars), 5)
        self.assertEqual(env_vars["AWS_LAMBDA_EXEC_WRAPPER"], "/opt/python/bin/elasticapm-lambda")
        self.assertIn("ELASTIC_APM_ENVIRONMENT", env_vars)
        self.assertEqual(env_vars["ELASTIC_APM_ENVIRONMENT"], "")

        # Verify that layers fallback to settings architecture (x86_64) when config fetch fails
        self.assertIn("Layers", call_kwargs)
        layers = call_kwargs["Layers"]
        expected_extension_layer = (
            "arn:aws:lambda:us-east-1:267093732750:layer:elastic-apm-extension-ver-1-6-0-x86_64:1"
        )
        self.assertIn(expected_extension_layer, layers)
