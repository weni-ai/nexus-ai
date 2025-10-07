import uuid
import logging
import time

from router.infrastructure.database.dynamo import get_message_table
from router.repositories import Repository
from router.repositories.entities import ResolutionEntities

logger = logging.getLogger(__name__)


class MessageRepository(Repository):

    def storage_message(
        self,
        project_uuid: str,
        contact_urn: str,
        message_data: dict,
        channel_uuid: str = None,
        resolution_status: int = ResolutionEntities.IN_PROGRESS,
        ttl_hours: int = 48
    ) -> None:
        """Store message with proper conversation and resolution tracking."""
        conversation_key = f"{project_uuid}#{contact_urn}#{channel_uuid}"
        message_timestamp = message_data["created_at"]
        message_id = str(uuid.uuid4())

        # Calculate TTL timestamp (current time + TTL hours)
        ttl_timestamp = int(time.time()) + (ttl_hours * 3600)

        with get_message_table() as table:
            item = {
                # Primary Keys
                "conversation_key": conversation_key,
                "message_timestamp": f"{message_timestamp}#{message_id}",

                # Attributes
                "conversation_id": conversation_key,
                "project_uuid": project_uuid,
                "contact_urn": contact_urn,
                "channel_uuid": channel_uuid,
                "message_id": message_id,
                "message_text": message_data["text"],
                "source_type": message_data["source"],
                "created_at": message_data["created_at"],
                "resolution_status": resolution_status,
                "ExpiresOn": ttl_timestamp,  # DynamoDB TTL attribute
            }

            table.put_item(Item=item)

    def get_messages(self, project_uuid: str, contact_urn: str) -> list:
        """Get all messages for a contact - maintains backward compatibility."""
        with get_message_table() as table:
            # Use scan for backward compatibility, but this should be replaced
            # with more specific queries in production
            response = table.scan(
                FilterExpression="project_uuid = :project AND contact_urn = :contact",
                ExpressionAttributeValues={
                    ":project": project_uuid,
                    ":contact": contact_urn
                },
            )

            return [
                {
                    "text": item["message_text"],
                    "source": item["source_type"],
                    "created_at": item["created_at"],
                }
                for item in response["Items"]
            ]

    def get_messages_for_conversation(
        self, project_uuid: str, contact_urn: str, channel_uuid: str,
        start_date: str, end_date: str, resolution_status: int = 2
    ) -> list:
        """Get messages for a specific conversation within time boundaries."""
        conversation_key = f"{project_uuid}#{contact_urn}#{channel_uuid}"

        with get_message_table() as table:
            # Build filter expression based on whether resolution_status is provided
            if resolution_status is not None:
                filter_expression = 'resolution_status = :resolution AND message_timestamp BETWEEN :start AND :end'
                expression_values = {
                    ':conv_key': conversation_key,
                    ':resolution': resolution_status,
                    ':start': start_date,
                    ':end': end_date
                }
            else:
                filter_expression = 'message_timestamp BETWEEN :start AND :end'
                expression_values = {
                    ':conv_key': conversation_key,
                    ':start': start_date,
                    ':end': end_date
                }

            response = table.query(
                IndexName='conversation-index',  # GSI2
                KeyConditionExpression='conversation_key = :conv_key',
                FilterExpression=filter_expression,
                ExpressionAttributeValues=expression_values,
                ScanIndexForward=True  # Chronological order
            )

            return [self._format_message(item) for item in response["Items"]]

    def get_unclassified_messages(
        self, project_uuid: str, contact_urn: str, channel_uuid: str
    ) -> list:
        """Get all unclassified messages for a conversation."""
        conversation_key = f"{project_uuid}#{contact_urn}#{channel_uuid}"

        with get_message_table() as table:
            response = table.query(
                IndexName='conversation-index',
                KeyConditionExpression='conversation_key = :conv_key',
                FilterExpression='resolution_status = :resolution',
                ExpressionAttributeValues={
                    ':conv_key': conversation_key,
                    ':resolution': 2  # Unclassified
                },
                ScanIndexForward=True
            )

            return [self._format_message(item) for item in response["Items"]]

    def update_messages_resolution(
        self, project_uuid: str, contact_urn: str, channel_uuid: str,
        start_date: str, end_date: str, new_resolution: int
    ) -> None:
        """Update resolution status for messages in a conversation."""
        conversation_key = f"{project_uuid}#{contact_urn}#{channel_uuid}"

        with get_message_table() as table:
            # Get messages to update
            response = table.query(
                IndexName='conversation-index',
                KeyConditionExpression='conversation_key = :conv_key',
                FilterExpression='message_timestamp BETWEEN :start AND :end',
                ExpressionAttributeValues={
                    ':conv_key': conversation_key,
                    ':start': start_date,
                    ':end': end_date
                }
            )

            # Batch update resolution status
            with table.batch_writer() as batch:
                for item in response["Items"]:
                    batch.put_item(
                        Item={
                            **item,
                            'resolution_status': new_resolution
                        }
                    )

    def _format_message(self, item: dict) -> dict:
        """Format message item for consistent output."""
        return {
            "text": item["message_text"],
            "source": item["source_type"],
            "created_at": item["created_at"],
        }

    def get_latest_message_by_source(
        self, project_uuid: str, contact_urn: str, source_type: str
    ) -> dict:
        """
        Get the most recent message by source type using DynamoDB scan.

        Args:
            project_uuid: Project unique identifier
            contact_urn: Contact unique resource name
            source_type: Message source type to filter by

        Returns:
            Most recent message data or empty dict if not found
        """
        with get_message_table() as table:
            response = table.scan(
                FilterExpression="project_uuid = :project AND contact_urn = :contact AND source_type = :source",
                ExpressionAttributeValues={
                    ":project": project_uuid,
                    ":contact": contact_urn,
                    ":source": source_type,
                },
            )

            items = response.get("Items", [])
            if items:
                sorted_items = sorted(
                    items, key=lambda x: x.get("created_at", ""), reverse=True
                )
                item = sorted_items[0]
                return {
                    "text": item["message_text"],
                    "source": item["source_type"],
                    "created_at": item["created_at"],
                }

            return {}

    def delete_messages(self, project_uuid: str, contact_urn: str, channel_uuid: str = None) -> None:
        """Delete all messages for a conversation."""
        conversation_key = f"{project_uuid}#{contact_urn}#{channel_uuid}"

        with get_message_table() as table:
            response = table.query(
                KeyConditionExpression='conversation_key = :conv_key',
                ExpressionAttributeValues={
                    ':conv_key': conversation_key
                }
            )

            if response["Items"]:
                with table.batch_writer() as batch:
                    for item in response["Items"]:
                        batch.delete_item(
                            Key={
                                "conversation_key": item["conversation_key"],
                                "message_timestamp": item["message_timestamp"],
                            }
                        )

    def delete_pending_tasks(self, project_uuid: str, contact_urn: str) -> None:
        """
        Delete pending tasks and task IDs for a conversation.

        Args:
            project_uuid: Project unique identifier
            contact_urn: Contact unique resource name
        """
        with get_message_table() as table:
            response = table.scan(
                FilterExpression="project_uuid = :project AND contact_urn = :contact AND (source_type = :pending OR source_type = :task_id)",
                ExpressionAttributeValues={
                    ":project": project_uuid,
                    ":contact": contact_urn,
                    ":pending": "pending",
                    ":task_id": "task_id",
                },
            )

            if response.get("Items"):
                with table.batch_writer() as batch:
                    for item in response["Items"]:
                        batch.delete_item(
                            Key={
                                "conversation_key": item["conversation_key"],
                                "message_timestamp": item["message_timestamp"],
                            }
                        )

    def add_message(self, project_uuid: str, contact_urn: str, message: dict, channel_uuid: str = None) -> None:
        """Add a single message to existing messages - matches Redis add_message functionality."""
        # For DynamoDB, we need to store each message individually
        # This is different from Redis where we store as a list
        self.storage_message(project_uuid, contact_urn, message, channel_uuid)

    def store_batch_messages(self, project_uuid: str, contact_urn: str, messages: list, key: str, channel_uuid: str = None) -> None:
        """Store a batch of messages with a custom key - matches Redis store_batch_messages functionality."""
        # For DynamoDB, we'll store each message individually with the custom key
        for message in messages:
            # Add the key to the message data for identification
            message_data = {
                "text": message.get("text", ""),
                "source": message.get("source", ""),
                "created_at": message.get("created_at", ""),
                "batch_key": key  # Add batch key for identification
            }
            self.storage_message(project_uuid, contact_urn, message_data, channel_uuid)
