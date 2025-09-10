import time

import uuid

import logging

from router.infrastructure.database.dynamo import get_message_table
from router.repositories import Repository

logger = logging.getLogger(__name__)


class MessageRepository(Repository):
    def storage_message(
        self, project_uuid: str, contact_urn: str, message_data: dict
    ) -> None:
        print(f"[DEBUG] Message data: {message_data}")

        with get_message_table() as table:
            conversation_id = f"{project_uuid}#{contact_urn}"
            ttl_timestamp = int(time.time()) + (2 * 24 * 60 * 60)

            item = {
                "UUID": str(uuid.uuid4()),
                "conversation_id": conversation_id,
                "message_timestamp": int(time.time()) * 1000,
                "project_uuid": project_uuid,
                "contact_urn": contact_urn,
                "message_text": message_data["text"],
                "source_type": message_data["source"],
                "created_at": message_data["created_at"],
                "ExpiresOn": ttl_timestamp,
            }

            print(f"[DEBUG] Item: {item}")

            table.put_item(Item=item)

    def get_messages(self, project_uuid: str, contact_urn: str) -> list:
        with get_message_table() as table:
            conversation_id = f"{project_uuid}#{contact_urn}"

            response = table.scan(
                FilterExpression="conversation_id = :conv_id",
                ExpressionAttributeValues={":conv_id": conversation_id},
            )

            return [
                {
                    "text": item["message_text"],
                    "source": item["source_type"],
                    "created_at": item["created_at"],
                }
                for item in response["Items"]
            ]

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
            conversation_id = f"{project_uuid}#{contact_urn}"

            response = table.scan(
                FilterExpression="conversation_id = :conv_id AND source_type = :source",
                ExpressionAttributeValues={
                    ":conv_id": conversation_id,
                    ":source": source_type,
                },
            )

            items = response.get("Items", [])
            if items:
                sorted_items = sorted(
                    items, key=lambda x: x.get("message_timestamp", 0), reverse=True
                )
                item = sorted_items[0]
                return {
                    "text": item["message_text"],
                    "source": item["source_type"],
                    "created_at": item["created_at"],
                }

            return {}

    def delete_messages(self, project_uuid: str, contact_urn: str) -> None:
        """Delete all messages for a conversation."""
        with get_message_table() as table:
            conversation_id = f"{project_uuid}#{contact_urn}"

            response = table.scan(
                FilterExpression="conversation_id = :conv_id",
                ExpressionAttributeValues={":conv_id": conversation_id},
            )

            with table.batch_writer() as batch:
                for item in response["Items"]:
                    batch.delete_item(
                        Key={
                            "UUID": item["UUID"],
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
            conversation_id = f"{project_uuid}#{contact_urn}"

            response = table.scan(
                FilterExpression="conversation_id = :conv_id AND (source_type = :pending OR source_type = :task_id)",
                ExpressionAttributeValues={
                    ":conv_id": conversation_id,
                    ":pending": "pending",
                    ":task_id": "task_id",
                },
            )

            if response.get("Items"):
                with table.batch_writer() as batch:
                    for item in response["Items"]:
                        batch.delete_item(
                            Key={
                                "UUID": item["UUID"],
                            }
                        )
