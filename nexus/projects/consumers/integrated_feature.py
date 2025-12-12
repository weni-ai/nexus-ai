import logging

import amqp
from sentry_sdk import capture_exception

from nexus.event_driven.consumer.consumers import EDAConsumer
from nexus.event_driven.parsers import JSONParser
from nexus.usecases.projects.create import CreateIntegratedFeatureUseCase
from nexus.usecases.projects.delete import delete_integrated_feature
from nexus.usecases.projects.dto import IntegratedFeatureDTO, IntegratedFeatureFlowDTO
from nexus.usecases.projects.update import UpdateIntegratedFeatureUseCase


class CreateIntegratedFeatureConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        try:
            logger.debug(
                "[IntegratedFeature] Consuming a message",
                extra={"body_len": len(message.body) if hasattr(message, "body") else None},
            )
            body = JSONParser.parse(message.body)
            integrated_feature_dto = IntegratedFeatureDTO(
                project_uuid=body.get("project_uuid"),
                feature_uuid=body.get("feature_uuid"),
                current_version_setup=body.get("action"),
            )
            usecase = CreateIntegratedFeatureUseCase()
            usecase.create_integrated_feature(integrated_feature_dto)

            message.channel.basic_ack(message.delivery_tag)
            logger.info("[IntegratedFeature] Feature created")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            logger.error("[IntegratedFeature] Message rejected", exc_info=True)


class IntegratedFeatureFlowConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        logger.debug(
            "[IntegratedFeatureFlows] Consuming a message",
            extra={"body_len": len(message.body) if hasattr(message, "body") else None},
        )
        try:
            body = JSONParser.parse(message.body)
            integrated_feature_dto = IntegratedFeatureFlowDTO(
                project_uuid=body.get("project_uuid"), feature_uuid=body.get("feature_uuid"), flows=body.get("flows")
            )
            usecase = CreateIntegratedFeatureUseCase()
            usecase.integrate_feature_flows(integrated_feature_dto)

            message.channel.basic_ack(message.delivery_tag)
            logger.info("[IntegratedFeatureFlows] Flow created")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            logger.error("[IntegratedFeatureFlows] Message rejected", exc_info=True)


class DeleteIntegratedFeatureConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        logger.debug(
            "[DeleteIntegratedFeature] Consuming a message",
            extra={"body_len": len(message.body) if hasattr(message, "body") else None},
        )
        try:
            body = JSONParser.parse(message.body)
            project_uuid = body.get("project_uuid")
            feature_uuid = body.get("feature_uuid")

            delete_integrated_feature(project_uuid=project_uuid, feature_uuid=feature_uuid)

            message.channel.basic_ack(message.delivery_tag)
            logger.info("[DeleteIntegratedFeature] IntegratedFeature deleted")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            logger.error("[DeleteIntegratedFeature] Message rejected", exc_info=True)


class UpdateIntegratedFeatureConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        logger.debug(
            "[UpdateIntegratedFeature] Consuming a message",
            extra={"body_len": len(message.body) if hasattr(message, "body") else None},
        )
        try:
            body = JSONParser.parse(message.body)
            usecase = UpdateIntegratedFeatureUseCase()
            usecase.update_integrated_feature(body)
            message.channel.basic_ack(message.delivery_tag)
            logger.info("[UpdateIntegratedFeature] Authorization created")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            logger.error("[UpdateIntegratedFeature] Message rejected", exc_info=True)


logger = logging.getLogger(__name__)
