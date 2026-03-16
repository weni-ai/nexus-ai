import logging
from io import BytesIO
from typing import Dict, List

import boto3
from django.conf import settings

logger = logging.getLogger(__name__)


class BedrockClient:
    def __init__(self):
        self.lambda_client = boto3.client("lambda", region_name=settings.AWS_BEDROCK_REGION_NAME)
        self.cloudwatch_client = boto3.client("logs", region_name=settings.AWS_BEDROCK_REGION_NAME)

    def _get_elastic_apm_layers(self, architecture: str = None) -> List[str]:
        """
        Get Elastic APM Lambda layers ARNs based on configuration.
        Returns empty list if APM is disabled or not configured.

        Args:
            architecture: Lambda architecture to use for layer ARNs (e.g. 'x86_64', 'arm64').
                          If not provided, falls back to AWS_LAMBDA_ARCHITECTURE setting.
        """
        if not getattr(settings, "ELASTIC_APM_LAMBDA_ENABLED", False):
            logger.info("ELASTIC_APM_LAMBDA not enabled")
            return []

        region = settings.AWS_BEDROCK_REGION_NAME
        if architecture is None:
            architecture = getattr(settings, "AWS_LAMBDA_ARCHITECTURE", "x86_64")
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
            logger.info("ELASTIC_APM_LAMBDA not enabled")
            return {}

        apm_server = getattr(settings, "ELASTIC_APM_LAMBDA_APM_SERVER", "")
        secret_token = getattr(settings, "ELASTIC_APM_LAMBDA_SECRET_TOKEN", "")
        apm_environment = getattr(settings, "ELASTIC_APM_ENVIRONMENT", "")
        apm_log_level = getattr(settings, "ELASTIC_APM_LAMBDA_LOG_LEVEL", "off")
        apm_service_name = getattr(settings, "ELASTIC_APM_SERVICE_NAME", "")

        if not apm_server or not secret_token:
            return {}

        return {
            "AWS_LAMBDA_EXEC_WRAPPER": "/opt/python/bin/elasticapm-lambda",
            "ELASTIC_APM_LAMBDA_APM_SERVER": apm_server,
            "ELASTIC_APM_SECRET_TOKEN": secret_token,
            "ELASTIC_APM_SEND_STRATEGY": "background",
            "ELASTIC_APM_ENVIRONMENT": apm_environment,
            "ELASTIC_APM_LOG_LEVEL": apm_log_level,
            "ELASTIC_APM_SERVICE_NAME": apm_service_name,
        }

    def create_lambda_function(
        self, lambda_name: str, lambda_role: str, skill_handler: str, zip_buffer: BytesIO
    ) -> Dict[str, str]:
        # Get Elastic APM layers and environment variables
        layers = self._get_elastic_apm_layers()
        environment_variables = self._get_elastic_apm_environment_variables()

        # Get Lambda architecture from settings
        lambda_architecture = getattr(settings, "AWS_LAMBDA_ARCHITECTURE", "x86_64")

        create_function_params = {
            "FunctionName": lambda_name,
            "Runtime": "python3.12",
            "Timeout": 180,
            "Role": lambda_role,
            "Code": {"ZipFile": zip_buffer.getvalue()},
            "Handler": skill_handler,
            "Architectures": [lambda_architecture],
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

    def _is_apm_layer(self, layer_arn: str) -> bool:
        """
        Check if a layer ARN is an Elastic APM layer.
        """
        return "elastic-apm" in layer_arn.lower()

    def _is_apm_environment_variable(self, var_name: str) -> bool:
        """
        Check if an environment variable name is an Elastic APM variable.
        """
        apm_var_names = {
            "AWS_LAMBDA_EXEC_WRAPPER",
            "ELASTIC_APM_LAMBDA_APM_SERVER",
            "ELASTIC_APM_SECRET_TOKEN",
            "ELASTIC_APM_SEND_STRATEGY",
            "ELASTIC_APM_ENVIRONMENT",
            "ELASTIC_APM_LOG_LEVEL",
            "ELASTIC_APM_SERVICE_NAME",
        }
        return var_name in apm_var_names

    def update_lambda_function(self, lambda_name: str, zip_buffer: BytesIO) -> Dict[str, str]:
        response = self.lambda_client.update_function_code(
            FunctionName=lambda_name, ZipFile=zip_buffer.getvalue(), Publish=True
        )
        waiter = self.lambda_client.get_waiter("function_updated")
        waiter.wait(FunctionName=lambda_name, WaiterConfig={"Delay": 5, "MaxAttempts": 60})
        new_version = response["Version"]
        lambda_arn = response["FunctionArn"]

        # Get current configuration to check if APM needs to be added/removed
        try:
            current_config = self.lambda_client.get_function_configuration(FunctionName=lambda_name)
            current_layers = current_config.get("Layers", [])
            current_layer_arns = [layer.get("Arn", "") for layer in current_layers if layer.get("Arn")]
            environment = current_config.get("Environment") or {}
            existing_vars = environment.get("Variables", {})
            # Read the actual architecture of the existing Lambda function
            current_architectures = current_config.get("Architectures", ["x86_64"])
            current_architecture = current_architectures[0] if current_architectures else "x86_64"
        except Exception as e:
            logger.error(
                "Failed to get current Lambda function configuration",
                extra={
                    "lambda_name": lambda_name,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
                exc_info=True,
            )
            current_layer_arns = []
            existing_vars = {}
            current_architecture = getattr(settings, "AWS_LAMBDA_ARCHITECTURE", "x86_64")

        # Get desired APM configuration using the Lambda's actual architecture
        desired_layers = self._get_elastic_apm_layers(architecture=current_architecture)
        desired_environment_variables = self._get_elastic_apm_environment_variables()

        # Check if we need to update configuration
        # We need to update if:
        # 1. APM is enabled and layers/env vars need to be added/updated
        # 2. APM is disabled but APM layers/env vars are still present (need to remove them)
        needs_update = False
        update_config_params = {"FunctionName": lambda_name}

        # Check layers: update if desired layers differ from current, or if APM layers need removal
        if desired_layers:
            # APM is enabled: merge desired APM layers with existing non-APM layers
            non_apm_layers = [arn for arn in current_layer_arns if not self._is_apm_layer(arn)]
            # Combine non-APM layers with desired APM layers (APM layers take precedence in case of duplicates)
            merged_layers = list(set(non_apm_layers + desired_layers))
            if set(merged_layers) != set(current_layer_arns):
                update_config_params["Layers"] = merged_layers
                needs_update = True
        else:
            # APM is disabled: remove APM layers if any are present
            apm_layers_present = any(self._is_apm_layer(arn) for arn in current_layer_arns)
            if apm_layers_present:
                # Remove APM layers, keep non-APM layers
                non_apm_layers = [arn for arn in current_layer_arns if not self._is_apm_layer(arn)]
                update_config_params["Layers"] = non_apm_layers
                needs_update = True

        # Check environment variables: update if desired vars differ from current, or if APM vars need removal
        if desired_environment_variables:
            # APM is enabled: merge with existing vars (APM vars take precedence)
            merged_vars = {**existing_vars, **desired_environment_variables}
            if merged_vars != existing_vars:
                update_config_params["Environment"] = {"Variables": merged_vars}
                needs_update = True
        else:
            # APM is disabled: remove APM variables if any are present
            apm_vars_present = any(self._is_apm_environment_variable(var_name) for var_name in existing_vars.keys())
            if apm_vars_present:
                # Remove APM variables, keep non-APM variables
                non_apm_vars = {
                    var_name: var_value
                    for var_name, var_value in existing_vars.items()
                    if not self._is_apm_environment_variable(var_name)
                }
                update_config_params["Environment"] = {"Variables": non_apm_vars}
                needs_update = True

        # Update configuration if needed
        if needs_update:
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
