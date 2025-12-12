import logging

import amqp
from sentry_sdk import capture_exception

from nexus.event_driven.consumer.consumers import EDAConsumer
from nexus.event_driven.parsers import JSONParser
from nexus.usecases.projects.create import ProjectAuthUseCase

logger = logging.getLogger(__name__)


class ProjectAuthConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        logger.debug(
            "[ProjectConsumer] Consuming a message",
            extra={"body_len": len(message.body) if hasattr(message, "body") else None},
        )
        try:
            body = JSONParser.parse(message.body)

            project_usecase = ProjectAuthUseCase()
            auth = project_usecase.create_project_auth(body)

            message.channel.basic_ack(message.delivery_tag)
            logger.info(
                "[ProjectConsumer] Authorization created",
                extra={"user_email": auth.user.email, "project": auth.project.name, "role": auth.role},
            )
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            logger.error("[ProjectConsumer] Message rejected", exc_info=True)
