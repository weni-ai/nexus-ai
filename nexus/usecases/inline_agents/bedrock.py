from io import BytesIO
from typing import Dict

import boto3
from django.conf import settings


class BedrockClient:
    def __init__(self):
        self.lambda_client = boto3.client(
            "lambda",
            region_name=settings.AWS_BEDROCK_REGION_NAME
        )
        self.cloudwatch_client = boto3.client(
            "logs",
            region_name=settings.AWS_BEDROCK_REGION_NAME
        )

    def create_lambda_function(
        self,
        lambda_name: str,
        lambda_role: str,
        skill_handler: str,
        zip_buffer: BytesIO
    ) -> Dict[str, str]:

        try:
            lambda_function = self.lambda_client.create_function(
                FunctionName=lambda_name,
                Runtime='python3.12',
                Timeout=180,
                Role=lambda_role,
                Code={'ZipFile': zip_buffer.getvalue()},
                Handler=skill_handler,
                LoggingConfig={
                    "LogGroup": settings.AWS_BEDROCK_LOG_GROUP,
                }
            )
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
            FunctionName=lambda_name,
            ZipFile=zip_buffer.getvalue(),
            Publish=True
        )
        waiter = self.lambda_client.get_waiter('function_updated')
        waiter.wait(
            FunctionName=lambda_name,
            WaiterConfig={
                'Delay': 5,
                'MaxAttempts': 60
            }
        )
        new_version = response['Version']
        lambda_arn = response['FunctionArn']

        self.update_lambda_alias(lambda_name, new_version)
        return {
            "lambda": lambda_arn
        }

    def update_lambda_alias(self, lambda_name: str, new_version: str):
        try:
            self.lambda_client.update_alias(
                FunctionName=lambda_name,
                Name='live',
                FunctionVersion=new_version
            )
        except self.lambda_client.exceptions.ResourceNotFoundException:
            self.lambda_client.create_alias(
                FunctionName=lambda_name,
                Name='live',
                FunctionVersion=new_version,
                Description='Production alias for the skill'
            )

    def get_log_group(self, tool_name: str) -> dict:
        response = self.cloudwatch_client.describe_log_groups(
            logGroupNamePrefix=f'/aws/lambda/{tool_name}',
            limit=1
        )

        log_group = response.get('logGroups', {})

        if log_group:
            return {
                "tool_name": tool_name,
                "log_group_name": log_group[0].get('logGroupName'),
                "log_group_arn": log_group[0].get('logGroupArn'),
            }

        return log_group
