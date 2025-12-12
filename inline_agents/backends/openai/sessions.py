import json
import logging
from typing import Any, Dict, List, Optional

import pendulum
import redis
import sentry_sdk
from agents.memory import Session
from django.conf import settings

TURN_ROLES = {"user", "assistant"}
TURN_TYPES = {"message_input_item", "message_output_item"}
WATERMARK_TYPE = "watermark"

logger = logging.getLogger(__name__)


def log_error_to_sentry(
    error: Exception, session_id: str, project_uuid: str, sanitized_urn: str, context: Dict[str, Any] = None
):
    try:
        sentry_context = {
            "session_id": session_id,
            "timestamp": pendulum.now().to_iso8601_string(),
            "error_type": type(error).__name__,
            "error_message": str(error),
            "project_uuid": project_uuid,
            "sanitized_urn": sanitized_urn,
        }

        if context:
            sentry_context.update(context)

        sentry_sdk.set_tag("project_uuid", project_uuid)
        sentry_sdk.set_tag("session_id", session_id)
        sentry_sdk.set_tag("error_type", type(error).__name__)

        sentry_sdk.set_context("session_error", sentry_context)

        sentry_sdk.capture_exception(error)

    except Exception as sentry_error:
        logger.error(f"Failed to log error to Sentry: {sentry_error}")


async def only_turns(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    out = []
    for item in items:
        role = item.get("role")
        turn_type = item.get("type") or item.get("item", {}).get("type")

        if role in TURN_ROLES and turn_type in TURN_TYPES:
            out.append(item)

    return out


async def get_watermark(session, ns: str) -> int:
    items = await session.get_items()

    for item in reversed(items):
        if item.get("type") == WATERMARK_TYPE and item.get("ns") == ns:
            return int(item.get("cursor", 0))

    return 0


async def set_watermark(session, ns: str, cursor: int):
    await session.add_items([{"type": WATERMARK_TYPE, "ns": ns, "cursor": int(cursor)}])


def sanitize_redis_item(item_str: str) -> str:
    """
    Sanitize Redis item by removing null characters before JSON parsing.

    Args:
        item_str: Raw string item from Redis that may contain null characters

    Returns:
        Clean string without null characters
    """
    if not isinstance(item_str, str):
        item_str = str(item_str)

    # Remove null characters that can cause JSON parsing issues
    sanitized = item_str.replace("\u0000", "").replace("\x00", "")

    return sanitized


class RedisSession(Session):
    def __init__(
        self, session_id: str, r: redis.Redis, project_uuid: str, sanitized_urn: str, limit: Optional[int] = None
    ):
        import logging

        logging.getLogger(__name__).debug("RedisSession", extra={"session_id": session_id})
        self._key = session_id
        self.r = r
        self.project_uuid = project_uuid
        self.sanitized_urn = sanitized_urn
        self.limit = limit

        if not self.is_connected():
            logger.error(f"Redis connection failed for session {session_id}")
            raise redis.ConnectionError(f"Redis connection failed for session {session_id}")

        self._initialize_key()

    def _initialize_key(self):
        with self.r.pipeline() as pipe:
            if not self.r.exists(self._key):
                pipe.lpush(self._key, "")
                pipe.expire(self._key, settings.AWS_BEDROCK_IDLE_SESSION_TTL_IN_SECONDS)
            else:
                pipe.expire(self._key, settings.AWS_BEDROCK_IDLE_SESSION_TTL_IN_SECONDS)
            pipe.execute()

    def get_session_id(self):
        return self._key

    def is_connected(self) -> bool:
        """Check if Redis connection is still active."""
        try:
            return self.r.ping()
        except redis.RedisError:
            return False

    async def get_items(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        limit = limit or self.limit
        import logging

        logging.getLogger(__name__).debug("Session limit", extra={"limit": limit})
        try:
            with self.r.pipeline() as pipe:
                if limit is None or limit <= 0:
                    pipe.lrange(self._key, 0, -1)
                else:
                    pipe.lrange(self._key, -limit, -1)

                pipe.expire(self._key, settings.AWS_BEDROCK_IDLE_SESSION_TTL_IN_SECONDS)
                results = pipe.execute()

                if not results or not results[0]:
                    return []

                data = results[0]

            items = []

            for i, raw_item in enumerate(data):
                try:
                    if raw_item:
                        raw_str = (
                            raw_item.decode("utf-8", errors="ignore") if isinstance(raw_item, bytes) else str(raw_item)
                        )

                        # Sanitize string to remove null characters before JSON parsing
                        sanitized_str = sanitize_redis_item(raw_str)

                        if len(raw_str) != len(sanitized_str):
                            null_count = raw_str.count("\u0000") + raw_str.count("\x00")
                            logger.warning(
                                f"Item {i} in session {self._key} contains {null_count} null characters. Sanitizing before parsing. "
                                f"Project: {self.project_uuid}, Contact: {self.sanitized_urn}"
                            )
                            log_error_to_sentry(
                                Exception(f"Session item contains {null_count} null characters"),
                                self._key,
                                self.project_uuid,
                                self.sanitized_urn,
                                {
                                    "item_index": i,
                                    "null_count": null_count,
                                    "raw_item_preview": raw_str[:200] if raw_str else None,
                                    "operation": "null_detection_and_sanitization",
                                },
                            )

                        parsed_item = json.loads(sanitized_str)
                        if isinstance(parsed_item, dict):
                            content = str(parsed_item.get("content", ""))
                            if content:
                                content_nulls = content.count("\u0000") + content.count("\x00")
                                if content_nulls > 0:
                                    logger.warning(
                                        f"Content of item {i} in session {self._key} contains {content_nulls} null characters. "
                                        f"Project: {self.project_uuid}, Contact: {self.sanitized_urn}"
                                    )

                            items.append(parsed_item)
                        else:
                            logger.warning(f"Item {i} in session {self._key} is not a dict: {type(parsed_item)}")
                except json.JSONDecodeError as e:
                    logger.error(f"Failed to parse JSON for item {i} in session {self._key}: {e}")
                    log_error_to_sentry(
                        e,
                        self._key,
                        self.project_uuid,
                        self.sanitized_urn,
                        {
                            "item_index": i,
                            "raw_item": str(raw_item)[:100] if raw_item else None,
                            "operation": "json_parse",
                        },
                    )
                    continue
                except Exception as e:
                    logger.error("Unexpected error parsing item %s in session %s: %s", i, self._key, e)
                    log_error_to_sentry(
                        e,
                        self._key,
                        self.project_uuid,
                        self.sanitized_urn,
                        {
                            "item_index": i,
                            "raw_item": str(raw_item)[:100] if raw_item else None,
                            "operation": "item_parse",
                        },
                    )
                    continue
            import logging

            logging.getLogger(__name__).debug("Session items", extra={"count": len(items)})
            return items

        except redis.RedisError as e:
            logger.error(f"Redis error retrieving items for session {self._key}: {e}")
            log_error_to_sentry(
                e, self._key, self.project_uuid, self.sanitized_urn, {"operation": "redis_operation", "limit": limit}
            )
            return []
        except Exception as e:
            logger.error(f"Unexpected error retrieving items for session {self._key}: {e}")
            log_error_to_sentry(
                e, self._key, self.project_uuid, self.sanitized_urn, {"operation": "get_items", "limit": limit}
            )
            return []

    async def add_items(self, items):
        pipe = self.r.pipeline()
        for item in items:
            pipe.rpush(self._key, json.dumps(item))
        pipe.execute()

    async def pop_item(self):
        raw = self.r.rpop(self._key)
        return json.loads(raw) if raw else None

    def clear_session(self):
        self.r.delete(self._key)


def make_session_factory(redis: redis.Redis, base_id: str, project_uuid: str, sanitized_urn: str, limit: int):
    def for_agent(agent_name: str | None = None):
        key = f"{base_id}:{agent_name}"
        return RedisSession(key, redis, project_uuid, sanitized_urn, limit)

    return for_agent
