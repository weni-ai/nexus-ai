import logging
import time
from typing import Optional

import boto3
from django.conf import settings

logger = logging.getLogger(__name__)


class SQSConnection:
    _instance: Optional["SQSConnection"] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance.connect()
        return cls._instance

    def _establish_connection(self):
        """Establish connection to SQS."""
        try:
            self.sqs_client = boto3.client(
                "sqs",
                region_name=settings.SQS_CONVERSATION_REGION,
            )
            logger.info(
                "[SQSConnection] SQS client initialized",
                extra={"region": settings.SQS_CONVERSATION_REGION},
            )
        except Exception as e:
            logger.error("Error while creating SQS client: %s", str(e), exc_info=True)
            raise

    def connect(self):
        """Connect to SQS, retrying if necessary."""
        try:
            if not hasattr(self, "sqs_client"):
                self._establish_connection()
        except Exception as e:
            logger.error("Error while connecting to SQS: %s", str(e), exc_info=True)
            time.sleep(5)
            self._establish_connection()

    def get_client(self):
        """Get SQS client, reconnecting if necessary."""
        try:
            if not hasattr(self, "sqs_client"):
                self._establish_connection()
            return self.sqs_client
        except Exception as e:
            logger.error("Error getting SQS client: %s", str(e), exc_info=True)
            self._establish_connection()
            return self.sqs_client

    def is_connected(self) -> bool:
        """Check if SQS connection is alive."""
        try:
            return hasattr(self, "sqs_client") and self.sqs_client is not None
        except Exception:
            return False
