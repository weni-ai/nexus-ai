import json
from typing import Optional

from redis import Redis

from router.repositories import Repository
from router.utils.redis_clients import get_redis_read_client, get_redis_write_client


class MessageRepository(Repository):
    """Redis implementation of message repository - simplified to match original functionality."""

    def __init__(self, redis_client: Optional[Redis] = None):
        if redis_client:
            self._read_client = redis_client
            self._write_client = redis_client
        else:
            self._read_client = get_redis_read_client()
            self._write_client = get_redis_write_client()

    def storage_message(
        self, project_uuid: str, contact_urn: str, message_data: dict, channel_uuid: str = None, ttl_hours: int = 48
    ) -> None:
        """Store a single message in Redis - matches original create_message_to_cache logic."""
        ttl_seconds = ttl_hours * 3600

        msg = [
            {"text": message_data["text"], "source": message_data["source"], "created_at": message_data["created_at"]}
        ]

        cache_key = f"conversation:{project_uuid}:{contact_urn}"
        self._write_client.setex(cache_key, ttl_seconds, json.dumps(msg))

    def get_messages(
        self, project_uuid: str, contact_urn: str, channel_uuid: str, limit: int = 50, cursor: str = None
    ) -> dict:
        """Get all messages for a conversation - uses read replica if available."""
        cache_key = f"conversation:{project_uuid}:{contact_urn}"
        messages = self._read_client.get(cache_key)
        if messages:
            message_list = json.loads(messages.decode("utf-8"))
            # For Redis, we'll return all messages in a paginated format
            # Apply limit if specified
            if limit and len(message_list) > limit:
                message_list = message_list[:limit]

            return {
                "items": message_list,
                "next_cursor": None,  # Redis doesn't support cursor-based pagination
                "total_count": len(message_list),
            }
        return {"items": [], "next_cursor": None, "total_count": 0}

    def add_message(self, project_uuid: str, contact_urn: str, message: dict, channel_uuid: str = None) -> None:
        """Add a single message to existing messages - matches original add_message_to_cache logic."""
        ttl = 172800  # 2 days
        cached_response = self.get_messages(project_uuid, contact_urn, channel_uuid)
        cached_messages = cached_response["items"]
        cached_messages.append(message)
        cache_key = f"conversation:{project_uuid}:{contact_urn}"
        self._write_client.setex(cache_key, ttl, json.dumps(cached_messages))

    def delete_messages(self, project_uuid: str, contact_urn: str, channel_uuid: str = None) -> None:
        """Clear all messages for a conversation - uses primary."""
        cache_key = f"conversation:{project_uuid}:{contact_urn}"
        self._write_client.delete(cache_key)

    def store_batch_messages(self, project_uuid: str, contact_urn: str, messages: list, key: str) -> None:
        """Store a batch of messages with a custom key - matches original rabbitmq_msg_batch_to_cache logic."""
        cache_key = f"{key}:{project_uuid}:{contact_urn}"
        ttl = 172800  # 2 days
        existing_msgs = self._read_client.get(cache_key)

        if existing_msgs:
            try:
                existing_msgs = json.loads(existing_msgs.decode("utf-8"))
                if isinstance(existing_msgs, list):
                    existing_msgs.extend(messages)
                else:
                    existing_msgs = messages
            except (json.JSONDecodeError, AttributeError):
                existing_msgs = messages
            self._write_client.setex(cache_key, ttl, json.dumps(existing_msgs))
        else:
            self._write_client.setex(cache_key, ttl, json.dumps(messages))
