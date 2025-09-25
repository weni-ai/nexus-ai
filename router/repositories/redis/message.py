import json

from router.repositories import Repository


class MessageRepository(Repository):
    """Redis implementation of message repository - simplified to match original functionality."""

    def __init__(self, redis_client):
        self.redis_client = redis_client

    def storage_message(
        self, project_uuid: str, contact_urn: str, message_data: dict
    ) -> None:
        """Store a single message in Redis - matches original create_message_to_cache logic."""
        ttl = 172800  # 2 days

        msg = [
            {
                "text": message_data["text"],
                "source": message_data["source"],
                "created_at": message_data["created_at"]
            }
        ]

        cache_key = f"conversation:{project_uuid}:{contact_urn}"
        self.redis_client.setex(
            cache_key,
            ttl,
            json.dumps(msg)
        )

    def get_messages(self, project_uuid: str, contact_urn: str) -> list:
        """Get all messages for a conversation - matches original get_cache_messages logic."""
        cache_key = f"conversation:{project_uuid}:{contact_urn}"
        messages = self.redis_client.get(cache_key)
        if messages:
            return json.loads(messages.decode('utf-8'))
        return []

    def add_message(self, project_uuid: str, contact_urn: str, message: dict) -> None:
        """Add a single message to existing messages - matches original add_message_to_cache logic."""
        cached_messages = self.get_messages(project_uuid, contact_urn)
        cached_messages.append(message)
        cache_key = f"conversation:{project_uuid}:{contact_urn}"
        self.redis_client.set(cache_key, json.dumps(cached_messages))

    def delete_messages(self, project_uuid: str, contact_urn: str) -> None:
        """Clear all messages for a conversation - matches original clear_message_cache logic."""
        cache_key = f"conversation:{project_uuid}:{contact_urn}"
        self.redis_client.delete(cache_key)

    def store_batch_messages(
        self,
        project_uuid: str,
        contact_urn: str,
        messages: list,
        key: str
    ) -> None:
        """Store a batch of messages with a custom key - matches original rabbitmq_msg_batch_to_cache logic."""
        cache_key = f"{key}:{project_uuid}:{contact_urn}"
        existing_msgs = self.redis_client.get(cache_key)

        if existing_msgs:
            try:
                existing_msgs = json.loads(existing_msgs.decode('utf-8'))
                if isinstance(existing_msgs, list):
                    existing_msgs.extend(messages)
                else:
                    existing_msgs = messages
            except (json.JSONDecodeError, AttributeError):
                existing_msgs = messages
            self.redis_client.set(cache_key, json.dumps(existing_msgs))
        else:
            self.redis_client.set(cache_key, json.dumps(messages))
