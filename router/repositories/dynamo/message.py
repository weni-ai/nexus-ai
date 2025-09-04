import time

import logging

from router.infrastructure.database.dynamo import get_message_table
from router.repositories import Repository

logger = logging.getLogger(__name__)


class MessageRepository(Repository):
    def __init__(self):
        self.table = get_message_table()

    def storage_message(
        self, project_uuid: str, contact_urn: str, message_data: dict
    ) -> None:
        with self.table as table:
            conversation_id = f"{project_uuid}#{contact_urn}"
            ttl_timestamp = int(time.time()) + (2 * 24 * 60 * 60)

            item = {
                "conversation_id": conversation_id,
                "message_timestamp": int(time.time()) * 1000,
                "project_uuid": project_uuid,
                "contact_urn": contact_urn,
                "message_text": message_data["text"],
                "source_type": message_data["source"],
                "created_at": message_data["created_at"],
                "ttl": ttl_timestamp,
            }

            table.put_item(Item=item)

    def get_messages(self, project_uuid: str, contact_urn: str) -> list:
        with self.table as table:
            conversation_id = f"{project_uuid}#{contact_urn}"

            response = table.query(
                KeyConditionExpression="conversation_id = :conv_id",
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

    def delete_messages(self, project_uuid: str, contact_urn: str) -> None:
        with self.table as table:
            conversation_id = f"{project_uuid}#{contact_urn}"

            response = table.query(
                KeyConditionExpression="conversation_id = :conv_id",
                ExpressionAttributeValues={":conv_id": conversation_id},
            )

            with table.batch_writer() as batch:
                for item in response["Items"]:
                    batch.delete_item(
                        Key={
                            "conversation_id": conversation_id,
                            "message_timestamp": item["message_timestamp"],
                        }
                    )
