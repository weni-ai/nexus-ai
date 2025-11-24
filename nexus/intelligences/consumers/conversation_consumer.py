import logging
import uuid

import amqp
from sentry_sdk import capture_exception

from nexus.event_driven.consumer.consumers import EDAConsumer
from nexus.event_driven.parsers import JSONParser
from nexus.intelligences.conversation_dto import WindowConversationDTO
from nexus.usecases.intelligences.lambda_usecase import create_lambda_conversation

logger = logging.getLogger(__name__)


class ConversationConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        # Generate correlation ID for tracking
        correlation_id = str(uuid.uuid4())
        delivery_tag = message.delivery_tag

        logger.info(
            "[ConversationConsumer] Starting message consumption",
            extra={
                "correlation_id": correlation_id,
                "delivery_tag": delivery_tag,
                "consumer": "ConversationConsumer",
                "message_body": message.body.decode() if message.body else None,
            },
        )

        try:
            body = JSONParser.parse(message.body)

            # Extract key identifiers
            project_uuid = body.get("project_uuid")
            contact_urn = body.get("contact_urn")
            external_id = body.get("id")
            channel_uuid = body.get("channel_uuid")

            window_conversation_dto = WindowConversationDTO(
                project_uuid=project_uuid,
                channel_uuid=channel_uuid,
                contact_urn=contact_urn,
                start_date=body.get("start"),
                end_date=body.get("end"),
                has_chats_room=body.get("has_chats_room"),
                external_id=external_id,
                name=body.get("contact_name"),
            )

            payload = window_conversation_dto.dict()
            payload["correlation_id"] = correlation_id

            task_result = create_lambda_conversation.delay(payload)
            task_id = task_result.id

            logger.info(
                "[ConversationConsumer] Message dispatched to Celery task",
                extra={
                    "correlation_id": correlation_id,
                    "task_id": task_id,
                    "delivery_tag": delivery_tag,
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "external_id": external_id,
                    "channel_uuid": channel_uuid,
                    "consumer": "ConversationConsumer",
                },
            )

            message.channel.basic_ack(delivery_tag)

            logger.info(
                "[ConversationConsumer] Message acknowledged successfully",
                extra={
                    "correlation_id": correlation_id,
                    "task_id": task_id,
                    "delivery_tag": delivery_tag,
                    "project_uuid": project_uuid,
                    "contact_urn": contact_urn,
                    "start_date": window_conversation_dto.start_date,
                    "end_date": window_conversation_dto.end_date,
                    "consumer": "ConversationConsumer",
                },
            )

        except KeyError as e:
            logger.error(
                "[ConversationConsumer] Message rejected - missing required field",
                extra={
                    "correlation_id": correlation_id,
                    "delivery_tag": delivery_tag,
                    "error": str(e),
                    "error_type": "KeyError",
                    "consumer": "ConversationConsumer",
                },
                exc_info=True,
            )
            capture_exception(e)
            message.channel.basic_reject(delivery_tag, requeue=False)

        except Exception as exception:
            logger.error(
                "[ConversationConsumer] Message rejected - unexpected error",
                extra={
                    "correlation_id": correlation_id,
                    "delivery_tag": delivery_tag,
                    "error": str(exception),
                    "error_type": type(exception).__name__,
                    "consumer": "ConversationConsumer",
                },
                exc_info=True,
            )
            capture_exception(exception)
            message.channel.basic_reject(delivery_tag, requeue=False)
