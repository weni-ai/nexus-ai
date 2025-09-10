import boto3

import logging

from functools import partial

from contextlib import contextmanager

from django.conf import settings

logger = logging.getLogger(__name__)


@contextmanager
def get_dynamodb_table(table_name: str):
    """
    Context manager that returns a DynamoDB table instance.
    """
    try:
        dynamodb = boto3.resource(
            "dynamodb",
            region_name=settings.DYNAMODB_REGION,
        )
        table = dynamodb.Table(table_name)
        yield table
    except Exception as e:
        logger.error(f"Error while getting DynamoDB table '{table_name}': {e}")
        raise e


get_message_table = partial(
    get_dynamodb_table, table_name=settings.DYNAMODB_MESSAGE_TABLE
)
