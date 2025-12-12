import logging

import amqp
from sentry_sdk import capture_exception

from nexus.event_driven.consumer.consumers import EDAConsumer
from nexus.event_driven.parsers import JSONParser
from nexus.projects.project_dto import FlowConsumerDTO
from nexus.usecases.actions import delete, retrieve
from nexus.usecases.projects.get_by_uuid import get_project_by_uuid


class FlowConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        logger.debug(
            "[FlowConsumer] Consuming a message",
            extra={"body_len": len(message.body) if hasattr(message, "body") else None},
        )
        try:
            body = JSONParser.parse(message.body)

            flow = FlowConsumerDTO(
                action=body["action"],
                entity=body["entity"],
                entity_name=body["entity_name"],
                user_email=body["user"],
                flow_organization=body["flow_organization"],
                entity_uuid=body["entity_uuid"],
                project_uuid=body["project_uuid"],
            )

            dto = delete.DeleteFlowDTO(flow_uuid=flow.entity_uuid)

            message.channel.basic_ack(message.delivery_tag)
            logger.info("[FlowConsumer] Flow read", extra={"flow": str(flow)})

            try:
                project = get_project_by_uuid(flow.project_uuid)
                usecase = delete.DeleteFlowsUseCase()
                usecase.hard_delete_flow(
                    flow_dto=dto,
                    project=project,
                )
                logger.info("[FlowConsumer] Flow deleted", extra={"entity_name": flow.entity_name})
            except retrieve.FlowDoesNotExist:
                logger.warning("[FlowConsumer] Flow not found", extra={"entity_name": flow.entity_name})

        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            logger.error("[FlowConsumer] Flow rejected", exc_info=True)


logger = logging.getLogger(__name__)
