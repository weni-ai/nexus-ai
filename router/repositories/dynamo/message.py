import uuid
import logging
import time
import base64
import json

import pendulum

from router.infrastructure.database.dynamo import get_message_table
from router.repositories import Repository
from router.repositories.entities import ResolutionEntities

logger = logging.getLogger(__name__)


class MessageRepository(Repository):

    def _convert_to_dynamo_sortable_timestamp(self, created_at: str) -> str:
        """
        Convert timestamp to consistent format for DynamoDB range queries.
        Normalizes timezone to UTC and removes timezone info for lexicographic sorting.
        """
        try:
            # Parse the timestamp (handles all ISO 8601 formats)
            dt = pendulum.parse(created_at)
            # Convert to UTC and format without timezone info for consistent lexicographic sorting
            return dt.in_timezone('UTC').format('YYYY-MM-DDTHH:mm:ss')
        except Exception as e:
            logger.warning(f"Failed to parse timestamp '{created_at}': {str(e)}. Using original value.")
            # Fallback: remove common timezone suffixes
            return created_at.replace('Z', '').replace('+00:00', '')

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

        # Convert created_at to DynamoDB sortable format for range queries
        sortable_timestamp = self._convert_to_dynamo_sortable_timestamp(message_data['created_at'])

        with get_message_table() as table:
            item = {
                # Primary Keys
                "conversation_key": conversation_key,
                "message_timestamp": f"{sortable_timestamp}#{message_id}",  # Sortable timestamp + UUID for uniqueness

                # Attributes
                "conversation_id": conversation_key,
                "project_uuid": project_uuid,
                "contact_urn": contact_urn,
                "channel_uuid": channel_uuid,
                "message_id": message_id,
                "message_text": message_data["text"],
                "source_type": message_data["source"],
                "created_at": sortable_timestamp,  # Use sortable timestamp for consistent range queries
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
        self,
        project_uuid: str,
        contact_urn: str,
        channel_uuid: str,
        start_date: str = None,
        end_date: str = None,
        resolution_status: int = None
    ) -> list:
        """Get messages for a specific conversation, optionally filtered by time range and resolution."""
        conversation_key = f"{project_uuid}#{contact_urn}#{channel_uuid}"

        with get_message_table() as table:
            # Build query parameters
            expression_values = {':conv_key': conversation_key}

            # Use KeyConditionExpression for efficient querying
            if start_date and end_date:
                start_sortable = self._convert_to_dynamo_sortable_timestamp(start_date)
                end_sortable = self._convert_to_dynamo_sortable_timestamp(end_date)
                # Use sort key in KeyConditionExpression for better performance
                key_condition = 'conversation_key = :conv_key AND message_timestamp BETWEEN :start AND :end'
                expression_values[':start'] = f"{start_sortable}#"
                expression_values[':end'] = f"{end_sortable}#"
            else:
                # No time range - just query by conversation
                key_condition = 'conversation_key = :conv_key'

            # Build FilterExpression only for non-key attributes
            filter_parts = []
            if resolution_status is not None:
                filter_parts.append('resolution_status = :resolution')
                expression_values[':resolution'] = resolution_status

            # Build query parameters
            query_params = {
                'KeyConditionExpression': key_condition,
                'ExpressionAttributeValues': expression_values,
                'ScanIndexForward': True  # Chronological order
            }

            # Only add FilterExpression if we have filters
            if filter_parts:
                query_params['FilterExpression'] = ' AND '.join(filter_parts)

            response = table.query(**query_params)

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
