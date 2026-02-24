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
        """Testa que quando APM está desabilitado, não adiciona layers nem variáveis de ambiente"""
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

        # Verifica que create_function foi chamado
        mock_lambda_client.create_function.assert_called_once()

        # Verifica que Layers não foi passado nos parâmetros
        call_args = mock_lambda_client.create_function.call_args
        self.assertNotIn("Layers", call_args.kwargs)

        # Verifica que Environment não foi passado nos parâmetros
        self.assertNotIn("Environment", call_args.kwargs)

        # Verifica que os parâmetros básicos estão presentes
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
        """Testa que quando APM está habilitado, adiciona layers e variáveis de ambiente corretamente"""
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

        # Verifica que create_function foi chamado
        mock_lambda_client.create_function.assert_called_once()

        # Verifica os parâmetros passados
        call_args = mock_lambda_client.create_function.call_args
        call_kwargs = call_args.kwargs

        # Verifica que Layers foi adicionado
        self.assertIn("Layers", call_kwargs)
        layers = call_kwargs["Layers"]
        self.assertEqual(len(layers), 2)

        # Verifica os ARNs das layers
        expected_extension_layer = (
            "arn:aws:lambda:us-east-1:267093732750:layer:elastic-apm-extension-ver-1-6-0-x86_64:1"
        )
        expected_python_agent_layer = "arn:aws:lambda:us-east-1:267093732750:layer:elastic-apm-python-ver-6-25-0:1"
        self.assertIn(expected_extension_layer, layers)
        self.assertIn(expected_python_agent_layer, layers)

        # Verifica que Environment foi adicionado
        self.assertIn("Environment", call_kwargs)
        environment = call_kwargs["Environment"]
        self.assertIn("Variables", environment)

        # Verifica as variáveis de ambiente
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
        """Testa que quando APM está habilitado mas falta server URL, não adiciona variáveis de ambiente"""
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

        # Verifica que Environment não foi adicionado quando falta configuração
        self.assertNotIn("Environment", call_kwargs)

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=True,
        ELASTIC_APM_LAMBDA_APM_SERVER="https://apm-server.example.com",
        ELASTIC_APM_LAMBDA_SECRET_TOKEN="",
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    def test_create_lambda_function_with_apm_enabled_but_missing_secret_token(self):
        """Testa que quando APM está habilitado mas falta secret token, não adiciona variáveis de ambiente"""
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

        # Verifica que Environment não foi adicionado quando falta configuração
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
        """Testa que a arquitetura arm64 é usada corretamente nos ARNs das layers"""
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

        # Verifica que Layers foi adicionado
        self.assertIn("Layers", call_kwargs)
        layers = call_kwargs["Layers"]

        # Verifica o ARN da extension layer com arm64
        expected_extension_layer = "arn:aws:lambda:us-west-2:267093732750:layer:elastic-apm-extension-ver-1-6-0-arm64:1"
        self.assertIn(expected_extension_layer, layers)

    @override_settings(
        ELASTIC_APM_LAMBDA_ENABLED=False,
        AWS_BEDROCK_REGION_NAME="us-east-1",
    )
    @patch.object(BedrockClient, "update_lambda_alias")
    def test_update_lambda_function_with_apm_disabled(self, mock_update_alias):
        """Testa que quando APM está desabilitado, update não adiciona layers nem variáveis"""
        mock_lambda_client = Mock()
        mock_lambda_client.update_function_code.return_value = {
            "Version": "1",
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function",
        }
        mock_lambda_client.get_waiter.return_value.wait = Mock()
        self.client.lambda_client = mock_lambda_client

        self.client.update_lambda_function(self.lambda_name, self.zip_buffer)

        # Verifica que update_function_configuration NÃO foi chamado
        mock_lambda_client.update_function_configuration.assert_not_called()
        # Verifica que update_lambda_alias foi chamado
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
        """Testa que update mescla variáveis de ambiente existentes com as do APM"""
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

        # Verifica que update_function_configuration foi chamado
        mock_lambda_client.update_function_configuration.assert_called_once()

        # Verifica os parâmetros passados
        call_args = mock_lambda_client.update_function_configuration.call_args
        call_kwargs = call_args.kwargs

        # Verifica que Layers foi adicionado
        self.assertIn("Layers", call_kwargs)
        layers = call_kwargs["Layers"]
        self.assertEqual(len(layers), 2)

        # Verifica que Environment foi adicionado com variáveis mescladas
        self.assertIn("Environment", call_kwargs)
        environment = call_kwargs["Environment"]
        env_vars = environment["Variables"]

        # Verifica que variáveis existentes foram preservadas
        self.assertEqual(env_vars["EXISTING_VAR"], "existing_value")
        self.assertEqual(env_vars["ANOTHER_VAR"], "another_value")

        # Verifica que variáveis do APM foram adicionadas
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
        """Testa que update funciona mesmo quando não há variáveis de ambiente existentes"""
        mock_lambda_client = Mock()
        mock_lambda_client.update_function_code.return_value = {
            "Version": "2",
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function",
        }
        mock_lambda_client.get_waiter.return_value.wait = Mock()
        mock_lambda_client.get_function_configuration.return_value = {
            "Environment": {"Variables": {}}  # Sem variáveis de ambiente existentes
        }
        self.client.lambda_client = mock_lambda_client

        self.client.update_lambda_function(self.lambda_name, self.zip_buffer)

        # Verifica que update_function_configuration foi chamado
        mock_lambda_client.update_function_configuration.assert_called_once()

        # Verifica os parâmetros passados
        call_args = mock_lambda_client.update_function_configuration.call_args
        call_kwargs = call_args.kwargs

        # Verifica que Environment foi adicionado apenas com variáveis do APM
        self.assertIn("Environment", call_kwargs)
        environment = call_kwargs["Environment"]
        env_vars = environment["Variables"]

        # Verifica que apenas variáveis do APM estão presentes
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
        """Testa que update trata exceções ao obter configuração atual"""
        mock_lambda_client = Mock()
        mock_lambda_client.update_function_code.return_value = {
            "Version": "2",
            "FunctionArn": "arn:aws:lambda:us-east-1:123456789012:function:test-lambda-function",
        }
        mock_lambda_client.get_waiter.return_value.wait = Mock()
        mock_lambda_client.get_function_configuration.side_effect = Exception("Config error")
        self.client.lambda_client = mock_lambda_client

        self.client.update_lambda_function(self.lambda_name, self.zip_buffer)

        # Verifica que update_function_configuration foi chamado mesmo com erro
        mock_lambda_client.update_function_configuration.assert_called_once()

        # Verifica que apenas variáveis do APM foram usadas (fallback)
        call_args = mock_lambda_client.update_function_configuration.call_args
        call_kwargs = call_args.kwargs
        env_vars = call_kwargs["Environment"]["Variables"]

        # Verifica que apenas variáveis do APM estão presentes
        self.assertEqual(len(env_vars), 4)
        self.assertEqual(env_vars["AWS_LAMBDA_EXEC_WRAPPER"], "/opt/python/bin/elasticapm-lambda")
