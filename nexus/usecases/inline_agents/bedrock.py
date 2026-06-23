import logging
from io import BytesIO
from typing import Dict, List, Optional, Tuple

import boto3
from django.conf import settings

logger = logging.getLogger(__name__)

APM_INSTRUMENTATION_ENABLED = "enabled"
APM_INSTRUMENTATION_DISABLED = "disabled"
APM_INSTRUMENTATION_UNCHANGED = "unchanged"
VALID_APM_INSTRUMENTATION = {
    APM_INSTRUMENTATION_ENABLED,
    APM_INSTRUMENTATION_DISABLED,
    APM_INSTRUMENTATION_UNCHANGED,
}


class APMNotConfiguredError(Exception):
    """Raised when APM instrumentation is requested but infrastructure is not available."""


class BedrockClient:
    def __init__(self):
        self.lambda_client = boto3.client("lambda", region_name=settings.AWS_BEDROCK_REGION_NAME)
        self.cloudwatch_client = boto3.client("logs", region_name=settings.AWS_BEDROCK_REGION_NAME)

    def _apm_infrastructure_available(self) -> bool:
        apm_server = getattr(settings, "ELASTIC_APM_LAMBDA_APM_SERVER", "")
        secret_token = getattr(settings, "ELASTIC_APM_LAMBDA_SECRET_TOKEN", "")
        return bool(apm_server and secret_token)

    def _resolve_apm_use_enabled(self, apm_instrumentation: str) -> Optional[bool]:
        if apm_instrumentation not in VALID_APM_INSTRUMENTATION:
            raise ValueError(
                f"Invalid apm_instrumentation value: {apm_instrumentation}. "
                f"Must be one of: {', '.join(sorted(VALID_APM_INSTRUMENTATION))}"
            )

        if apm_instrumentation == APM_INSTRUMENTATION_ENABLED:
            if not self._apm_infrastructure_available():
                raise APMNotConfiguredError(
                    "Elastic APM is not configured in this environment. "
                    "Contact your platform administrator."
                )
            return True

        if apm_instrumentation == APM_INSTRUMENTATION_DISABLED:
            return False

        return None

    def _get_elastic_apm_layers(self, architecture: str = None, *, use_apm: bool) -> List[str]:
        """
        Get Elastic APM Lambda layers ARNs based on configuration.
        Returns empty list if APM is not requested or not configured.

        Args:
            architecture: Lambda architecture to use for layer ARNs (e.g. 'x86_64', 'arm64').
                          If not provided, falls back to AWS_LAMBDA_ARCHITECTURE setting.
            use_apm: Whether APM instrumentation should be applied.
        """
        if not use_apm or not self._apm_infrastructure_available():
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

    def _get_elastic_apm_environment_variables(self, *, use_apm: bool) -> Dict[str, str]:
        """
        Get Elastic APM Lambda environment variables.
        Returns empty dict if APM is not requested or not configured.
        """
        if not use_apm or not self._apm_infrastructure_available():
            return {}

        apm_server = getattr(settings, "ELASTIC_APM_LAMBDA_APM_SERVER", "")
        secret_token = getattr(settings, "ELASTIC_APM_LAMBDA_SECRET_TOKEN", "")
        apm_environment = getattr(settings, "ELASTIC_APM_ENVIRONMENT", "")
        apm_log_level = getattr(settings, "ELASTIC_APM_LAMBDA_LOG_LEVEL", "off")

        return {
            "AWS_LAMBDA_EXEC_WRAPPER": "/opt/python/bin/elasticapm-lambda",
            "ELASTIC_APM_LAMBDA_APM_SERVER": apm_server,
            "ELASTIC_APM_SECRET_TOKEN": secret_token,
            "ELASTIC_APM_SEND_STRATEGY": "background",
            "ELASTIC_APM_ENVIRONMENT": apm_environment,
            "ELASTIC_APM_LOG_LEVEL": apm_log_level,
        }

    def _apply_apm_configuration_updates(
        self,
        update_config_params: Dict,
        *,
        use_apm: Optional[bool],
        current_layer_arns: List[str],
        existing_vars: Dict[str, str],
        architecture: str,
    ) -> bool:
        needs_update = False

        if use_apm is None:
            return False

        desired_layers = self._get_elastic_apm_layers(architecture=architecture, use_apm=use_apm)
        desired_environment_variables = self._get_elastic_apm_environment_variables(use_apm=use_apm)

        if desired_layers:
            non_apm_layers = [arn for arn in current_layer_arns if not self._is_apm_layer(arn)]
            merged_layers = list(set(non_apm_layers + desired_layers))
            if set(merged_layers) != set(current_layer_arns):
                update_config_params["Layers"] = merged_layers
                needs_update = True
        else:
            apm_layers_present = any(self._is_apm_layer(arn) for arn in current_layer_arns)
            if apm_layers_present:
                non_apm_layers = [arn for arn in current_layer_arns if not self._is_apm_layer(arn)]
                update_config_params["Layers"] = non_apm_layers
                needs_update = True

        if desired_environment_variables:
            merged_vars = {**existing_vars, **desired_environment_variables}
            if merged_vars != existing_vars:
                update_config_params["Environment"] = {"Variables": merged_vars}
                needs_update = True
        else:
            apm_vars_present = any(self._is_apm_environment_variable(var_name) for var_name in existing_vars.keys())
            if apm_vars_present:
                non_apm_vars = {
                    var_name: var_value
                    for var_name, var_value in existing_vars.items()
                    if not self._is_apm_environment_variable(var_name)
                }
                update_config_params["Environment"] = {"Variables": non_apm_vars}
                needs_update = True

        return needs_update

    def create_lambda_function(
        self,
        lambda_name: str,
        lambda_role: str,
        skill_handler: str,
        zip_buffer: BytesIO,
        apm_instrumentation: str = APM_INSTRUMENTATION_UNCHANGED,
    ) -> Dict[str, str]:
        use_apm = self._resolve_apm_use_enabled(apm_instrumentation)
        apply_apm = use_apm is True

        layers = self._get_elastic_apm_layers(use_apm=apply_apm)
        environment_variables = self._get_elastic_apm_environment_variables(use_apm=apply_apm)

        lambda_architecture = getattr(settings, "AWS_LAMBDA_ARCHITECTURE", "x86_64")
        lambda_memory_size = getattr(settings, "AWS_LAMBDA_MEMORY_SIZE", 512)

        create_function_params = {
            "FunctionName": lambda_name,
            "Runtime": "python3.12",
            "Timeout": 180,
            "Role": lambda_role,
            "Code": {"ZipFile": zip_buffer.getvalue()},
            "Handler": skill_handler,
            "Architectures": [lambda_architecture],
            "MemorySize": lambda_memory_size,
        }

        if layers:
            create_function_params["Layers"] = layers

        if environment_variables:
            create_function_params["Environment"] = {"Variables": environment_variables}

        log_group = getattr(settings, "AWS_LAMBDA_LOG_GROUP", "")
        if log_group:
            create_function_params["LoggingConfig"] = {"LogGroup": log_group}

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

        self.lambda_client.delete_function(FunctionName=function_name)

    def _is_apm_layer(self, layer_arn: str) -> bool:
        return "elastic-apm" in layer_arn.lower()

    def _is_apm_environment_variable(self, var_name: str) -> bool:
        apm_var_names = {
            "AWS_LAMBDA_EXEC_WRAPPER",
            "ELASTIC_APM_LAMBDA_APM_SERVER",
            "ELASTIC_APM_SECRET_TOKEN",
            "ELASTIC_APM_SEND_STRATEGY",
            "ELASTIC_APM_ENVIRONMENT",
            "ELASTIC_APM_LOG_LEVEL",
        }
        return var_name in apm_var_names

    def _wait_for_function_updated(self, lambda_name: str) -> None:
        waiter = self.lambda_client.get_waiter("function_updated")
        waiter.wait(FunctionName=lambda_name, WaiterConfig={"Delay": 5, "MaxAttempts": 60})

    def _read_lambda_configuration(self, lambda_name: str) -> Tuple[Dict, List[str], Dict[str, str], str, int]:
        current_config = self.lambda_client.get_function_configuration(FunctionName=lambda_name)
        current_layers = current_config.get("Layers", [])
        current_layer_arns = [layer.get("Arn", "") for layer in current_layers if layer.get("Arn")]
        environment = current_config.get("Environment") or {}
        existing_vars = environment.get("Variables", {})
        current_architectures = current_config.get("Architectures", ["x86_64"])
        current_architecture = current_architectures[0] if current_architectures else "x86_64"
        current_memory_size = current_config.get("MemorySize", 128)
        return current_config, current_layer_arns, existing_vars, current_architecture, current_memory_size

    def _apply_non_apm_configuration_updates(
        self,
        lambda_name: str,
        current_config: Dict,
        current_memory_size: int,
    ) -> None:
        desired_memory_size = getattr(settings, "AWS_LAMBDA_MEMORY_SIZE", 512)

        needs_update = False
        update_config_params = {"FunctionName": lambda_name}

        if current_memory_size != desired_memory_size:
            update_config_params["MemorySize"] = desired_memory_size
            needs_update = True

        desired_log_group = getattr(settings, "AWS_LAMBDA_LOG_GROUP", "")
        if desired_log_group:
            current_log_group = current_config.get("LoggingConfig", {}).get("LogGroup", "")
            if current_log_group != desired_log_group:
                update_config_params["LoggingConfig"] = {"LogGroup": desired_log_group}
                needs_update = True

        if needs_update:
            self.lambda_client.update_function_configuration(**update_config_params)

    def _apply_apm_configuration_before_publish(
        self,
        lambda_name: str,
        *,
        use_apm: bool,
        apm_action: str,
    ) -> None:
        try:
            _, current_layer_arns, existing_vars, current_architecture, _ = self._read_lambda_configuration(
                lambda_name
            )
        except Exception as e:
            logger.error(
                "Failed to get current Lambda function configuration for %s",
                lambda_name,
                extra={
                    "lambda_name": lambda_name,
                    "error_type": type(e).__name__,
                    "error_message": str(e),
                },
                exc_info=True,
            )
            raise RuntimeError(
                f"Cannot update APM configuration for Lambda {lambda_name}: "
                "failed to read current function configuration"
            ) from e

        update_config_params = {"FunctionName": lambda_name}
        needs_apm_update = self._apply_apm_configuration_updates(
            update_config_params,
            use_apm=use_apm,
            current_layer_arns=current_layer_arns,
            existing_vars=existing_vars,
            architecture=current_architecture,
        )

        if needs_apm_update:
            logger.info(
                "Applying APM configuration before publish for %s (apm_action=%s)",
                lambda_name,
                apm_action,
            )
            self.lambda_client.update_function_configuration(**update_config_params)
            self._wait_for_function_updated(lambda_name)
        elif use_apm is True:
            logger.info(
                "No APM configuration changes required for %s (APM already enabled)",
                lambda_name,
            )
        elif use_apm is False:
            logger.info(
                "No APM configuration changes required for %s (APM already disabled)",
                lambda_name,
            )

    def update_lambda_function(
        self,
        lambda_name: str,
        zip_buffer: BytesIO,
        apm_instrumentation: str = APM_INSTRUMENTATION_UNCHANGED,
    ) -> Dict[str, str]:
        """
        Update Lambda code and optionally control APM instrumentation.

        - enabled (--use-apm): add APM layers/vars if missing, then publish code
        - disabled (--remove-apm): remove APM layers/vars, then publish code
        - unchanged (no flag): publish code only; APM state is not modified
        """
        use_apm = self._resolve_apm_use_enabled(apm_instrumentation)
        apm_action = "enable" if use_apm is True else "disable" if use_apm is False else "unchanged"
        logger.info(
            "Updating Lambda function %s (apm_instrumentation=%s, apm_action=%s)",
            lambda_name,
            apm_instrumentation,
            apm_action,
        )

        if use_apm is not None:
            self._apply_apm_configuration_before_publish(lambda_name, use_apm=use_apm, apm_action=apm_action)

        response = self.lambda_client.update_function_code(
            FunctionName=lambda_name, ZipFile=zip_buffer.getvalue(), Publish=True
        )
        self._wait_for_function_updated(lambda_name)
        new_version = response["Version"]
        lambda_arn = response["FunctionArn"]

        logger.info(
            "Published Lambda version %s for %s (apm_action=%s)",
            new_version,
            lambda_name,
            apm_action,
        )

        try:
            current_config, _, _, _, current_memory_size = self._read_lambda_configuration(lambda_name)
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
            current_config = {}
            current_memory_size = 128

        self._apply_non_apm_configuration_updates(lambda_name, current_config, current_memory_size)

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
        log_group_name = getattr(settings, "AWS_LAMBDA_LOG_GROUP", "")

        if not log_group_name:
            log_group_name = f"/aws/lambda/{tool_name}"

        response = self.cloudwatch_client.describe_log_groups(logGroupNamePrefix=log_group_name, limit=1)

        log_groups = response.get("logGroups", [])

        if log_groups and log_groups[0].get("logGroupName") == log_group_name:
            return {
                "tool_name": tool_name,
                "lambda_name": tool_name,
                "log_group_name": log_groups[0].get("logGroupName"),
                "log_group_arn": log_groups[0].get("logGroupArn"),
            }

        return {}
