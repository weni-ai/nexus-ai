from io import BytesIO
from typing import Dict, List

import boto3
from django.conf import settings


class BedrockClient:
    def __init__(self):
        self.lambda_client = boto3.client("lambda", region_name=settings.AWS_BEDROCK_REGION_NAME)
        self.cloudwatch_client = boto3.client("logs", region_name=settings.AWS_BEDROCK_REGION_NAME)

    def _get_elastic_apm_layers(self) -> List[str]:
        """
        Get Elastic APM Lambda layers ARNs based on configuration.
        Returns empty list if APM is disabled or not configured.
        """
        if not getattr(settings, "ELASTIC_APM_LAMBDA_ENABLED", False):
            return []

        region = settings.AWS_BEDROCK_REGION_NAME
        architecture = getattr(settings, "ELASTIC_APM_LAMBDA_ARCHITECTURE", "x86_64")
        extension_version = getattr(settings, "ELASTIC_APM_LAMBDA_EXTENSION_VERSION", "1-6-0")
        python_agent_version = getattr(settings, "ELASTIC_APM_LAMBDA_PYTHON_AGENT_VERSION", "6-25-0")

        # Elastic APM layer ARNs format:
        # Extension: arn:aws:lambda:{region}:267093732750:layer:elastic-apm-extension-ver-{version}-{arch}:1
        # Python Agent: arn:aws:lambda:{region}:267093732750:layer:elastic-apm-python-ver-{version}:1
        extension_layer_arn = (
            f"arn:aws:lambda:{region}:267093732750:layer:elastic-apm-extension-ver-{extension_version}-{architecture}:1"
        )
        python_agent_layer_arn = (
            f"arn:aws:lambda:{region}:267093732750:layer:elastic-apm-python-ver-{python_agent_version}:1"
        )

        return [extension_layer_arn, python_agent_layer_arn]

    def _get_elastic_apm_environment_variables(self) -> Dict[str, str]:
        """
        Get Elastic APM Lambda environment variables.
        Returns empty dict if APM is disabled or not configured.
        """
        if not getattr(settings, "ELASTIC_APM_LAMBDA_ENABLED", False):
            return {}

        apm_server = getattr(settings, "ELASTIC_APM_LAMBDA_APM_SERVER", "")
        secret_token = getattr(settings, "ELASTIC_APM_LAMBDA_SECRET_TOKEN", "")

        if not apm_server or not secret_token:
            return {}

        return {
            "AWS_LAMBDA_EXEC_WRAPPER": "/opt/python/bin/elasticapm-lambda",
            "ELASTIC_APM_LAMBDA_APM_SERVER": apm_server,
            "ELASTIC_APM_SECRET_TOKEN": secret_token,
            "ELASTIC_APM_SEND_STRATEGY": "background",
        }

    def create_lambda_function(
        self, lambda_name: str, lambda_role: str, skill_handler: str, zip_buffer: BytesIO
    ) -> Dict[str, str]:
        # Get Elastic APM layers and environment variables
        layers = self._get_elastic_apm_layers()
        environment_variables = self._get_elastic_apm_environment_variables()

        create_function_params = {
            "FunctionName": lambda_name,
            "Runtime": "python3.12",
            "Timeout": 180,
            "Role": lambda_role,
            "Code": {"ZipFile": zip_buffer.getvalue()},
            "Handler": skill_handler,
        }

        # Add layers if Elastic APM is enabled
        if layers:
            create_function_params["Layers"] = layers

        # Add environment variables if Elastic APM is enabled
        if environment_variables:
            create_function_params["Environment"] = {"Variables": environment_variables}

        try:
            lambda_function = self.lambda_client.create_function(**create_function_params)
            lambda_arn = lambda_function.get("FunctionArn")
        except self.lambda_client.exceptions.ResourceConflictException:
            lambda_function = self.lambda_client.get_function(FunctionName=lambda_name)
            lambda_arn = lambda_function.get("FunctionArn")

        return lambda_arn

    def delete_lambda_function(self, function_name: str):
        list_aliases = self.lambda_client.list_aliases(FunctionName=function_name)
        aliases = list_aliases.get("Aliases")

        for alias in aliases:
            self.lambda_client.delete_alias(FunctionName=function_name, Name=alias.get("Name"))

        # list_versions_by_function = self.lambda_client.list_versions_by_function(FunctionName=function_name)
        # list_versions_by_function["Versions"][0]["Version"]
        self.lambda_client.delete_function(FunctionName=function_name)

    def update_lambda_function(self, lambda_name: str, zip_buffer: BytesIO) -> Dict[str, str]:
        response = self.lambda_client.update_function_code(
            FunctionName=lambda_name, ZipFile=zip_buffer.getvalue(), Publish=True
        )
        waiter = self.lambda_client.get_waiter("function_updated")
        waiter.wait(FunctionName=lambda_name, WaiterConfig={"Delay": 5, "MaxAttempts": 60})
        new_version = response["Version"]
        lambda_arn = response["FunctionArn"]

        # Update layers and environment variables if Elastic APM is enabled
        layers = self._get_elastic_apm_layers()
        environment_variables = self._get_elastic_apm_environment_variables()

        if layers or environment_variables:
            update_config_params = {"FunctionName": lambda_name}
            if layers:
                update_config_params["Layers"] = layers
            if environment_variables:
                # Get existing environment variables to merge with APM variables
                try:
                    current_config = self.lambda_client.get_function_configuration(FunctionName=lambda_name)
                    environment = current_config.get("Environment") or {}
                    existing_vars = environment.get("Variables", {})
                    # Merge existing variables with APM variables (APM variables take precedence)
                    merged_vars = {**existing_vars, **environment_variables}
                    update_config_params["Environment"] = {"Variables": merged_vars}
                except Exception:
                    # If we can't get current config, just use APM variables
                    update_config_params["Environment"] = {"Variables": environment_variables}

            self.lambda_client.update_function_configuration(**update_config_params)

        self.update_lambda_alias(lambda_name, new_version)
        return {"lambda": lambda_arn}

    def update_lambda_alias(self, lambda_name: str, new_version: str):
        try:
            self.lambda_client.update_alias(FunctionName=lambda_name, Name="live", FunctionVersion=new_version)
        except self.lambda_client.exceptions.ResourceNotFoundException:
            self.lambda_client.create_alias(
                FunctionName=lambda_name,
                Name="live",
                FunctionVersion=new_version,
                Description="Production alias for the skill",
            )

    def get_log_group(self, tool_name: str) -> dict:
        response = self.cloudwatch_client.describe_log_groups(logGroupNamePrefix=f"/aws/lambda/{tool_name}", limit=1)

        log_group = response.get("logGroups", {})

        if log_group:
            return {
                "tool_name": tool_name,
                "log_group_name": log_group[0].get("logGroupName"),
                "log_group_arn": log_group[0].get("logGroupArn"),
            }

        return log_group
