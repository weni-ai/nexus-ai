import pendulum
import json


from typing import Optional
from redis import Redis
from django.conf import settings

from router.tasks.interfaces import InlineAgentTaskManager


class RedisTaskManager(InlineAgentTaskManager):
    """Redis implementation of inline agent task management."""

    CACHE_TIMEOUT = 300  # 5 minutes in seconds

    def __init__(self, redis_client: Optional[Redis] = None):
        self.redis_client = redis_client or Redis.from_url(settings.REDIS_URL)

    def get_pending_response(
        self, project_uuid: str, contact_urn: str
    ) -> Optional[str]:
        """Get the pending response for a contact."""
        pending_response_key = f"response:{project_uuid}:{contact_urn}"
        pending_response = self.redis_client.get(pending_response_key)
        return pending_response.decode("utf-8") if pending_response else None

    def get_pending_task_id(self, project_uuid: str, contact_urn: str) -> Optional[str]:
        """Get the pending task ID for a contact."""
        pending_task_key = f"task:{project_uuid}:{contact_urn}"
        pending_task_id = self.redis_client.get(pending_task_key)
        return pending_task_id.decode("utf-8") if pending_task_id else None

    def store_pending_response(
        self, project_uuid: str, contact_urn: str, message_text: str
    ) -> None:
        """Store a pending response for a contact."""
        pending_response_key = f"response:{project_uuid}:{contact_urn}"
        self.redis_client.set(pending_response_key, message_text)

    def store_pending_task_id(
        self, project_uuid: str, contact_urn: str, task_id: str
    ) -> None:
        """Store a pending task ID for a contact."""
        pending_task_key = f"task:{project_uuid}:{contact_urn}"
        self.redis_client.set(pending_task_key, task_id)

    def clear_pending_tasks(self, project_uuid: str, contact_urn: str) -> None:
        """Clear all pending tasks for a contact."""
        pending_response_key = f"response:{project_uuid}:{contact_urn}"
        pending_task_key = f"task:{project_uuid}:{contact_urn}"
        self.redis_client.delete(pending_response_key)
        self.redis_client.delete(pending_task_key)

    def handle_pending_response(
        self, project_uuid: str, contact_urn: str, message_text: str
    ) -> str:
        """
        Handle pending response by either concatenating with existing response
        or storing new response.
        Returns the final message text to be processed.
        """
        pending_response = self.get_pending_response(project_uuid, contact_urn)

        if pending_response:
            # Concatenate the previous message with the new one
            final_message = f"{pending_response}\n{message_text}"
            self.clear_pending_tasks(project_uuid, contact_urn)
        else:
            # Store the current message
            final_message = message_text
            self.store_pending_response(project_uuid, contact_urn, message_text)

        return final_message

    def get_rationale_session_data(self, session_id: str) -> dict:
        """Get or create rationale session data from cache."""
        cache_key = f"rationale_session_{session_id}"
        session_data = self.redis_client.get(cache_key)

        if session_data is None:
            session_data = {
                "rationale_history": [],
                "first_rationale_text": None,
                "is_first_rationale": True,
            }
            self.save_rationale_session_data(session_id, session_data)
        else:
            session_data = eval(session_data.decode("utf-8"))

        return session_data

    def save_rationale_session_data(self, session_id: str, session_data: dict) -> None:
        """Save rationale session data to cache."""
        cache_key = f"rationale_session_{session_id}"
        self.redis_client.setex(cache_key, self.CACHE_TIMEOUT, str(session_data))

    def create_message_to_cache(
        self,
        msg_text: str,
        contact_urn: str,
        contact_name: str,
        project_uuid: str,
        source: str,
        channel_uuid: str = None,
    ) -> None:
        from nexus.usecases.intelligences.create import ConversationUseCase

        ttl = 172800  # 2 days

        msg = [
            {
                "text": msg_text,
                "source": source,
                "created_at": pendulum.now().to_iso8601_string(),
            }
        ]

        cache_key = f"conversation:{project_uuid}:{contact_urn}"
        self.redis_client.setex(cache_key, ttl, json.dumps(msg))

        usecase = ConversationUseCase()
        usecase.create_conversation_base_structure(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            contact_name=contact_name,
            channel_uuid=channel_uuid,
        )

    def get_cache_messages(self, project_uuid: str, contact_urn: str) -> list:
        """Get messages from cache"""
        cache_key = f"conversation:{project_uuid}:{contact_urn}"
        messages = self.redis_client.get(cache_key)
        if messages:
            return json.loads(messages.decode("utf-8"))
        return []

    def add_message_to_cache(
        self, project_uuid: str, contact_urn: str, msg_text: str, source: str
    ) -> None:
        from nexus.usecases.intelligences.create import ConversationUseCase

        cached_messages = self.get_cache_messages(project_uuid, contact_urn)
        cached_messages.append(
            {
                "text": msg_text,
                "source": source,
                "created_at": pendulum.now().to_iso8601_string(),
            }
        )
        self.redis_client.set(
            f"conversation:{project_uuid}:{contact_urn}", json.dumps(cached_messages)
        )

        conversation_usecase = ConversationUseCase()
        conversation_usecase.conversation_in_progress_exists(
            project_uuid=project_uuid,
            contact_urn=contact_urn,
            channel_uuid=channel_uuid,
            contact_name=contact_name
        )

    def handle_message_cache(
        self,
        contact_urn: str,
        contact_name: str,
        project_uuid: str,
        msg_text: str,
        source: str,
        channel_uuid: str = None,
        preview: bool = False,
    ) -> None:
        print("="*100)
        print("[DEBUG] handle_message_cache")
        if project_uuid not in settings.CUSTOM_LAMBDA_CONVERSATION_PROJECTS:
            return

        if preview:
            return

        cached_messages = self.get_cache_messages(project_uuid, contact_urn)
        print("[DEBUG] cached_messages", cached_messages)
        if cached_messages:
            print("[DEBUG] add_message_to_cache")
            self.add_message_to_cache(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                msg_text=msg_text,
                source=source,
            )
        else:
            print("[DEBUG] create_message_to_cache")
            self.create_message_to_cache(
                project_uuid=project_uuid,
                contact_urn=contact_urn,
                contact_name=contact_name,
                msg_text=msg_text,
                source=source,
                channel_uuid=channel_uuid,
            )
        print("="*100)

    def clear_message_cache(self, project_uuid: str, contact_urn: str) -> None:
        """Clear message cache"""
        self.redis_client.delete(f"conversation:{project_uuid}:{contact_urn}")

    def rabbitmq_msg_batch_to_cache(
        self, project_uuid: str, contact_urn: str, messages: list, key: str
    ) -> None:
        """
        Store a batch of messages in cache.
        """
        cache_key = f"{key}:{project_uuid}:{contact_urn}"
        existing_msgs = self.redis_client.get(cache_key)

        if existing_msgs:
            try:
                existing_msgs = json.loads(existing_msgs.decode("utf-8"))
                if isinstance(existing_msgs, list):
                    existing_msgs.extend(messages)
                else:
                    existing_msgs = messages
            except (json.JSONDecodeError, AttributeError):
                existing_msgs = messages
            self.redis_client.set(cache_key, json.dumps(existing_msgs))
        else:
            self.redis_client.set(cache_key, json.dumps(messages))
