import logging

import amqp
from django.db import IntegrityError
from sentry_sdk import capture_exception

from nexus.event_driven.consumer.consumers import EDAConsumer
from nexus.event_driven.parsers import JSONParser
from nexus.projects.channel_ops import create_channel_from_wwc_event
from nexus.projects.models import Project

logger = logging.getLogger(__name__)


class ChannelWwcConsumer(EDAConsumer):
    """Consumes WWC channel create events (exchange channel-events.topic, routing key wwc-create)."""

    def consume(self, message: amqp.Message):
        logger.debug(
            f"[ChannelWwcConsumer] Consuming a message, body: {message.body}",
        )
        channel_uuid = project_uuid = None
        try:
            body = JSONParser.parse(message.body)
            action = body.get("action")
            if action is not None:
                logger.debug("[ChannelWwcConsumer] action=%s", action)

            channel_uuid = body.get("uuid")
            project_uuid = body.get("project_uuid")
            channel_type = body.get("channel_type")

            if not channel_uuid or not project_uuid or channel_type is None or channel_type == "":
                logger.warning(
                    f"[ChannelWwcConsumer] Missing required fields: {body}",
                )
                message.channel.basic_reject(message.delivery_tag, requeue=False)
                return

            create_channel_from_wwc_event(
                project_uuid=str(project_uuid),
                channel_uuid=str(channel_uuid),
                channel_type=str(channel_type),
            )
            message.channel.basic_ack(message.delivery_tag)
            logger.info(
                f"[ChannelWwcConsumer] Channel created, project_uuid: {project_uuid}, channel_uuid: {channel_uuid}",
            )
        except IntegrityError as exc:
            capture_exception(exc)
            message.channel.basic_ack(message.delivery_tag)
            logger.warning(
                f"[ChannelWwcConsumer] Duplicate channel uuid (IntegrityError), channel_uuid: {channel_uuid}",
            )
        except (Project.DoesNotExist, ValueError) as exc:
            message.channel.basic_ack(message.delivery_tag)
            logger.warning("[ChannelWwcConsumer] Skipping message: %s", exc)
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            logger.error("[ChannelWwcConsumer] Message rejected", exc_info=True)
