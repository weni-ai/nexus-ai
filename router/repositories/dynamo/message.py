import uuid
import logging
import time
import base64
import json

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
        message_id = str(uuid.uuid4())

        # Calculate TTL timestamp (current time + TTL hours)
        ttl_timestamp = int(time.time()) + (ttl_hours * 3600)

        with get_message_table() as table:
            item = {
                # Primary Keys
                "conversation_key": conversation_key,
                "message_timestamp": f"{message_data['created_at']}#{message_id}",  # Use created_at for better querying

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

    def get_messages(self, project_uuid: str, contact_urn: str, channel_uuid: str, limit: int = 50, cursor: str = None) -> dict:
        """Get messages with pagination - optimized for large datasets."""
        conversation_key = f"{project_uuid}#{contact_urn}#{channel_uuid}"

        with get_message_table() as table:
            # Build query parameters
            query_params = {
                'KeyConditionExpression': 'conversation_key = :conv_key',
                'ExpressionAttributeValues': {
                    ':conv_key': conversation_key
                },
                'Limit': limit,
                'ScanIndexForward': False  # Get newest messages first
            }

            # Add cursor if provided
            if cursor:
                try:
                    exclusive_start_key = json.loads(base64.b64decode(cursor).decode('utf-8'))
                    query_params['ExclusiveStartKey'] = exclusive_start_key
                except Exception as e:
                    logger.warning(f"Invalid cursor: {str(e)}")
                    # Continue without cursor

            try:
                response = table.query(**query_params)

                # Format messages
                messages = []
                for item in response.get('Items', []):
                    messages.append(self._format_message(item))

                # Create next cursor if there are more items
                next_cursor = None
                if 'LastEvaluatedKey' in response:
                    next_cursor = base64.b64encode(
                        json.dumps(response['LastEvaluatedKey']).encode('utf-8')
                    ).decode('utf-8')

                return {
                    'items': messages,
                    'next_cursor': next_cursor,
                    'total_count': len(messages)
                }

            except Exception as e:
                logger.error(f"Error querying messages: {str(e)}")
                raise e

    def get_messages_for_conversation(
        self, project_uuid: str, contact_urn: str, channel_uuid: str,
        start_date: str, end_date: str, resolution_status: int = 2
    ) -> list:
        """Get messages for a specific conversation within time boundaries."""
        conversation_key = f"{project_uuid}#{contact_urn}#{channel_uuid}"

        with get_message_table() as table:
            # Use KeyConditionExpression for time filtering since message_timestamp now contains created_at
            key_condition = 'conversation_key = :conv_key AND message_timestamp BETWEEN :start AND :end'
            expression_values = {
                ':conv_key': conversation_key,
                ':start': f"{start_date}#",  # Start of time range
                ':end': f"{end_date}#"       # End of time range
            }

            # Add resolution filter if specified
            if resolution_status is not None:
                filter_expression = 'resolution_status = :resolution'
                expression_values[':resolution'] = resolution_status
            else:
                filter_expression = None

            response = table.query(
                IndexName='conversation-index',  # GSI2
                KeyConditionExpression=key_condition,
                FilterExpression=filter_expression,
                ExpressionAttributeValues=expression_values,
                ScanIndexForward=True  # Chronological order
            )

            return [self._format_message(item) for item in response["Items"]]

    def _format_message(self, item: dict) -> dict:
        """Format message item for consistent output."""
        return {
            "text": item["message_text"],
            "source": item["source_type"],
            "created_at": item["created_at"],
        }

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

    def add_message(self, project_uuid: str, contact_urn: str, message: dict, channel_uuid: str = None) -> None:
        """Add a single message to existing messages - matches Redis add_message functionality."""
        # For DynamoDB, we need to store each message individually
        # This is different from Redis where we store as a list
        self.storage_message(project_uuid, contact_urn, message, channel_uuid)

    def store_batch_messages(self, project_uuid: str, contact_urn: str, messages: list, key: str, channel_uuid: str = None) -> None:

        # Not used, future implementation.
        raise NotImplementedError("Store batch messages is not implemented for DynamoDB.")
