import json
import logging
import uuid
from datetime import datetime, timezone
from time import sleep
from typing import Dict, List, Optional, Tuple

from botocore.exceptions import ClientError
from django.conf import settings

from nexus.event_driven.connection.sqs_connection import SQSConnection

logger = logging.getLogger(__name__)


class SQSPublisher:
    def __init__(self) -> None:
        self.sqs_connection = SQSConnection()
        self.queue_url = settings.SQS_CONVERSATION_QUEUE_URL
        self.dlq_url = settings.SQS_CONVERSATION_DLQ_URL

    def _generate_message_group_id(
        self,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: Optional[str],
        message_timestamp: Optional[datetime] = None,
    ) -> str:
        """
        Generate Message Group ID with 20-second time window for parallelism.

        Messages created within the same 20-second window share the same group ID,
        allowing parallel processing between different time windows while maintaining
        order within each window.

        Args:
            project_uuid: Project UUID
            contact_urn: Contact URN
            channel_uuid: Channel UUID (optional)
            message_timestamp: Timestamp when the message was created (from message.created_at)

        Returns:
            Message Group ID string
        """
        base_id = f"{project_uuid}:{contact_urn}"
        if channel_uuid:
            base_id += f":{channel_uuid}"

        if message_timestamp:
            # Create 20-second time window: divide timestamp by 20 seconds
            # This groups messages created within the same 20-second window
            timestamp_seconds = int(message_timestamp.timestamp())
            window_number = timestamp_seconds // 20  # 20-second windows
            base_id += f":window_{window_number}"
        else:
            # Fallback: use current time if timestamp not provided
            # This should rarely happen, but provides backward compatibility
            current_timestamp = datetime.now(timezone.utc)
            timestamp_seconds = int(current_timestamp.timestamp())
            window_number = timestamp_seconds // 20
            base_id += f":window_{window_number}"
            logger.warning(
                "[SQSPublisher] Message timestamp not provided, using current time for Message Group ID",
                extra={"project_uuid": project_uuid, "contact_urn": contact_urn},
            )

        return base_id

    def _generate_deduplication_id(self, correlation_id: str) -> str:
        """
        Generate Deduplication ID to prevent duplicate messages.
        Within 5-minute window, messages with same ID are deduplicated.
        """
        return correlation_id

    def send_message(
        self,
        body: Dict,
        event_type: str,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Send message to SQS FIFO queue.

        Args:
            body: Message body (will be JSON serialized)
            event_type: Type of event (message.received, message.sent, etc.)
            project_uuid: Project UUID
            contact_urn: Contact URN
            channel_uuid: Channel UUID (optional)
            correlation_id: Correlation ID for tracking (optional, will generate if not provided)

        Returns:
            Message ID if successful, None otherwise
        """
        if not settings.SQS_CONVERSATION_ENABLED:
            logger.debug(
                "[SQSPublisher] SQS disabled, skipping message",
                extra={"event_type": event_type, "project_uuid": project_uuid},
            )
            return None

        if not self.queue_url:
            logger.warning("[SQSPublisher] Queue URL not configured, skipping message")
            return None

        if not correlation_id:
            correlation_id = str(uuid.uuid4())

        # Extract message timestamp from body for time-window based Message Group ID
        message_timestamp = None
        try:
            # Try to extract timestamp from message.created_at in the body
            message_data = body.get("data", {})
            message_info = message_data.get("message", {})
            created_at_str = message_info.get("created_at")

            if created_at_str:
                # Parse ISO format timestamp
                if isinstance(created_at_str, str):
                    # Try parsing ISO format
                    try:
                        # Handle different ISO formats
                        timestamp_str = created_at_str.replace("Z", "+00:00")
                        message_timestamp = datetime.fromisoformat(timestamp_str)
                        # Convert to UTC if timezone-aware, or assume UTC if naive
                        if message_timestamp.tzinfo is None:
                            # If naive datetime, assume UTC
                            message_timestamp = message_timestamp.replace(tzinfo=timezone.utc)
                        else:
                            # Convert to UTC
                            message_timestamp = message_timestamp.astimezone(timezone.utc)
                    except (ValueError, AttributeError):
                        # Fallback: try parsing with pendulum if available
                        try:
                            import pendulum

                            message_timestamp = pendulum.parse(created_at_str)
                            if isinstance(message_timestamp, pendulum.DateTime):
                                message_timestamp = message_timestamp.to_datetime()
                            # Ensure UTC
                            if message_timestamp.tzinfo is None:
                                message_timestamp = message_timestamp.replace(tzinfo=timezone.utc)
                            else:
                                message_timestamp = message_timestamp.astimezone(timezone.utc)
                        except Exception:
                            logger.warning(
                                "[SQSPublisher] Could not parse message timestamp, using current time",
                                extra={"created_at": created_at_str},
                            )
        except Exception as e:
            logger.debug(
                "[SQSPublisher] Error extracting message timestamp: %s",
                str(e),
                extra={"project_uuid": project_uuid},
            )

        message_group_id = self._generate_message_group_id(project_uuid, contact_urn, channel_uuid, message_timestamp)
        deduplication_id = self._generate_deduplication_id(correlation_id)

        message_attributes = {
            "event_type": {"StringValue": event_type, "DataType": "String"},
            "project_uuid": {"StringValue": project_uuid, "DataType": "String"},
        }

        if channel_uuid:
            message_attributes["channel_uuid"] = {"StringValue": channel_uuid, "DataType": "String"}

        sended = False
        retry_count = 0
        max_retries = 3

        while not sended and retry_count < max_retries:
            try:
                sqs_client = self.sqs_connection.get_client()

                response = sqs_client.send_message(
                    QueueUrl=self.queue_url,
                    MessageBody=json.dumps(body),
                    MessageGroupId=message_group_id,
                    MessageDeduplicationId=deduplication_id,
                    MessageAttributes=message_attributes,
                )

                sended = True

                logger.info(
                    "[SQSPublisher] Message sent successfully",
                    extra={
                        "message_id": response.get("MessageId"),
                        "correlation_id": correlation_id,
                        "event_type": event_type,
                        "message_group_id": message_group_id,
                        "project_uuid": project_uuid,
                        "contact_urn": contact_urn,
                        "channel_uuid": channel_uuid,
                    },
                )

                return response.get("MessageId")

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code")
                error_message = e.response.get("Error", {}).get("Message", str(e))

                logger.error(
                    "[SQSPublisher] SQS publish error",
                    extra={
                        "error_code": error_code,
                        "error_message": error_message,
                        "correlation_id": correlation_id,
                        "event_type": event_type,
                        "retry_count": retry_count,
                    },
                    exc_info=True,
                )

                # Retry on transient errors
                if error_code in ["Throttling", "ServiceUnavailable", "InternalError"]:
                    retry_count += 1
                    if retry_count < max_retries:
                        sleep_time = settings.EDA_WAIT_TIME_RETRY * retry_count
                        logger.info(
                            "[SQSPublisher] Retrying after %s seconds",
                            sleep_time,
                            extra={"retry_count": retry_count},
                        )
                        sleep(sleep_time)
                        self.sqs_connection._establish_connection()
                    else:
                        logger.error(
                            "[SQSPublisher] Max retries reached, giving up",
                            extra={"correlation_id": correlation_id, "event_type": event_type},
                        )
                        return None
                else:
                    logger.error(
                        "[SQSPublisher] Permanent error, not retrying",
                        extra={"error_code": error_code, "correlation_id": correlation_id},
                    )
                    return None

            except Exception as err:
                logger.error(
                    "[SQSPublisher] Unexpected error: %s",
                    str(err),
                    extra={"correlation_id": correlation_id, "event_type": event_type},
                    exc_info=True,
                )
                retry_count += 1
                if retry_count < max_retries:
                    sleep(settings.EDA_WAIT_TIME_RETRY)
                    self.sqs_connection._establish_connection()
                else:
                    return None

        return None

    def send_message_batch(
        self,
        messages: List[Dict],
    ) -> Tuple[int, int, List[str]]:
        """
        Send multiple messages to SQS FIFO queue using SendMessageBatch API.
        Maximum 10 messages per batch (SQS limit).

        Args:
            messages: List of message dicts, each containing:
                - body: Message body (will be JSON serialized)
                - event_type: Type of event
                - project_uuid: Project UUID
                - contact_urn: Contact URN
                - channel_uuid: Channel UUID (optional)
                - correlation_id: Correlation ID (optional)

        Returns:
            Tuple of (successful_count, failed_count, message_ids)
        """
        if not settings.SQS_CONVERSATION_ENABLED:
            logger.debug("[SQSPublisher] SQS disabled, skipping batch")
            return 0, len(messages), []

        if not self.queue_url:
            logger.warning("[SQSPublisher] Queue URL not configured, skipping batch")
            return 0, len(messages), []

        if len(messages) > 10:
            logger.warning("[SQSPublisher] Batch size exceeds SQS limit (10), truncating to 10 messages")
            messages = messages[:10]

        entries = []
        message_ids_map = {}  # Map entry ID to correlation_id for tracking

        for idx, msg_data in enumerate(messages):
            body = msg_data.get("body", {})
            event_type = msg_data.get("event_type", "message.received")
            project_uuid = msg_data.get("project_uuid")
            contact_urn = msg_data.get("contact_urn")
            channel_uuid = msg_data.get("channel_uuid")
            correlation_id = msg_data.get("correlation_id") or str(uuid.uuid4())

            if not project_uuid or not contact_urn:
                logger.warning(f"[SQSPublisher] Skipping message {idx}: missing project_uuid or contact_urn")
                continue

            # Extract message timestamp from body for time-window based Message Group ID
            message_timestamp = None
            try:
                # Try to extract timestamp from message.created_at in the body
                message_data = body.get("data", {})
                message_info = message_data.get("message", {})
                created_at_str = message_info.get("created_at")

                if created_at_str:
                    # Parse ISO format timestamp
                    if isinstance(created_at_str, str):
                        try:
                            # Handle different ISO formats
                            timestamp_str = created_at_str.replace("Z", "+00:00")
                            message_timestamp = datetime.fromisoformat(timestamp_str)
                            # Convert to UTC if timezone-aware, or assume UTC if naive
                            if message_timestamp.tzinfo is None:
                                # If naive datetime, assume UTC
                                from datetime import timezone

                                message_timestamp = message_timestamp.replace(tzinfo=timezone.utc)
                            else:
                                # Convert to UTC
                                message_timestamp = message_timestamp.astimezone(timezone.utc)
                        except (ValueError, AttributeError):
                            # Fallback: try parsing with pendulum if available
                            try:
                                import pendulum

                                message_timestamp = pendulum.parse(created_at_str)
                                if isinstance(message_timestamp, pendulum.DateTime):
                                    message_timestamp = message_timestamp.to_datetime()
                                # Ensure UTC
                                if message_timestamp.tzinfo is None:
                                    message_timestamp = message_timestamp.replace(tzinfo=timezone.utc)
                                else:
                                    message_timestamp = message_timestamp.astimezone(timezone.utc)
                            except Exception:
                                logger.debug(
                                    "[SQSPublisher] Could not parse message timestamp in batch",
                                    extra={"created_at": created_at_str},
                                )
            except Exception as e:
                logger.debug(
                    "[SQSPublisher] Error extracting message timestamp in batch: %s",
                    str(e),
                )

            message_group_id = self._generate_message_group_id(
                project_uuid, contact_urn, channel_uuid, message_timestamp
            )
            deduplication_id = self._generate_deduplication_id(correlation_id)

            message_attributes = {
                "event_type": {"StringValue": event_type, "DataType": "String"},
                "project_uuid": {"StringValue": project_uuid, "DataType": "String"},
            }

            if channel_uuid:
                message_attributes["channel_uuid"] = {"StringValue": channel_uuid, "DataType": "String"}

            entry_id = f"msg-{idx}"
            entries.append(
                {
                    "Id": entry_id,
                    "MessageBody": json.dumps(body),
                    "MessageGroupId": message_group_id,
                    "MessageDeduplicationId": deduplication_id,
                    "MessageAttributes": message_attributes,
                }
            )
            message_ids_map[entry_id] = correlation_id

        if not entries:
            logger.warning("[SQSPublisher] No valid messages to send in batch")
            return 0, len(messages), []

        retry_count = 0
        max_retries = 3

        while retry_count < max_retries:
            try:
                sqs_client = self.sqs_connection.get_client()

                response = sqs_client.send_message_batch(QueueUrl=self.queue_url, Entries=entries)

                successful = response.get("Successful", [])
                failed = response.get("Failed", [])

                successful_count = len(successful)
                failed_count = len(failed)

                message_ids = [msg.get("MessageId") for msg in successful]

                logger.info(
                    "[SQSPublisher] Batch sent successfully",
                    extra={
                        "successful": successful_count,
                        "failed": failed_count,
                        "total": len(entries),
                    },
                )

                if failed:
                    for failure in failed:
                        logger.warning(
                            "[SQSPublisher] Message failed in batch",
                            extra={
                                "id": failure.get("Id"),
                                "code": failure.get("Code"),
                                "message": failure.get("Message"),
                            },
                        )

                return successful_count, failed_count, message_ids

            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code")
                error_message = e.response.get("Error", {}).get("Message", str(e))

                logger.error(
                    "[SQSPublisher] SQS batch publish error",
                    extra={
                        "error_code": error_code,
                        "error_message": error_message,
                        "retry_count": retry_count,
                        "batch_size": len(entries),
                    },
                    exc_info=True,
                )

                # Retry on transient errors
                if error_code in ["Throttling", "ServiceUnavailable", "InternalError"]:
                    retry_count += 1
                    if retry_count < max_retries:
                        sleep_time = settings.EDA_WAIT_TIME_RETRY * retry_count
                        logger.info(
                            "[SQSPublisher] Retrying batch after %s seconds",
                            sleep_time,
                            extra={"retry_count": retry_count},
                        )
                        sleep(sleep_time)
                        self.sqs_connection._establish_connection()
                    else:
                        logger.error("[SQSPublisher] Max retries reached for batch")
                        return 0, len(entries), []
                else:
                    logger.error(
                        "[SQSPublisher] Permanent error in batch, not retrying",
                        extra={"error_code": error_code},
                    )
                    return 0, len(entries), []

            except Exception as err:
                logger.error(
                    "[SQSPublisher] Unexpected error in batch: %s",
                    str(err),
                    exc_info=True,
                )
                retry_count += 1
                if retry_count < max_retries:
                    sleep(settings.EDA_WAIT_TIME_RETRY)
                    self.sqs_connection._establish_connection()
                else:
                    return 0, len(entries), []

        return 0, len(entries), []
