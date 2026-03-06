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

        message_body = message.body.decode() if message.body else None
        logger.info(
            f"[ConversationConsumer] Starting message consumption - "
            f"correlation_id={correlation_id}, delivery_tag={delivery_tag}, "
            f"message_body={message_body}"
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
                f"[ConversationConsumer] Message dispatched to Celery task - "
                f"correlation_id={correlation_id}, task_id={task_id}, "
                f"delivery_tag={delivery_tag}, project_uuid={project_uuid}, "
                f"contact_urn={contact_urn}, external_id={external_id}, "
                f"channel_uuid={channel_uuid}"
            )

            message.channel.basic_ack(delivery_tag)

            logger.info(
                f"[ConversationConsumer] Message acknowledged successfully - "
                f"correlation_id={correlation_id}, task_id={task_id}, "
                f"delivery_tag={delivery_tag}, project_uuid={project_uuid}, "
                f"contact_urn={contact_urn}, start_date={window_conversation_dto.start_date}, "
                f"end_date={window_conversation_dto.end_date}"
            )

        except KeyError as e:
            logger.error(
                f"[ConversationConsumer] Message rejected - missing required field - "
                f"correlation_id={correlation_id}, delivery_tag={delivery_tag}, "
                f"error={str(e)}, error_type=KeyError",
                exc_info=True,
            )
            capture_exception(e)
            message.channel.basic_reject(delivery_tag, requeue=False)

        except Exception as exception:
            error_type = type(exception).__name__
            logger.error(
                f"[ConversationConsumer] Message rejected - unexpected error - "
                f"correlation_id={correlation_id}, delivery_tag={delivery_tag}, "
                f"error={str(exception)}, error_type={error_type}",
                exc_info=True,
            )
            capture_exception(exception)
            message.channel.basic_reject(delivery_tag, requeue=False)
