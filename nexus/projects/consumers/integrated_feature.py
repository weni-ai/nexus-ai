import amqp
from sentry_sdk import capture_exception

from nexus.event_driven.parsers import JSONParser
from nexus.event_driven.consumer.consumers import EDAConsumer

from nexus.usecases.projects.create import CreateIntegratedFeatureUseCase
from nexus.usecases.projects.delete import delete_integrated_feature
from nexus.usecases.projects.update import UpdateIntegratedFeatureUseCase


class CreateIntegratedFeatureConsumer(EDAConsumer):

    def consume(self, message: amqp.Message):
        try:
            print(f"[IntegratedFeature] - Consuming a message. Body: {message.body}")
            body = JSONParser.parse(message.body)

            usecase = CreateIntegratedFeatureUseCase()
            usecase.create_integrated_feature(body)

            message.channel.basic_ack(message.delivery_tag)
            print("[IntegratedFeature] - Feature created")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[IntegratedFeature] - Message rejected by: {exception}")


class IntegratedFeatureFlowConsumer(EDAConsumer):

    def consume(self, message: amqp.Message):
        print(f"[IntegratedFeatureFlows] - Consuming a message. Body: {message.body}")
        try:
            body = JSONParser.parse(message.body)

            usecase = CreateIntegratedFeatureUseCase()
            usecase.integrate_feature_flows(body)

            message.channel.basic_ack(message.delivery_tag)
            print("[IntegratedFeatureFlows] - IntegratedFeatureFlows flow created")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[IntegratedFeatureFlows] - Message rejected by: {exception}")


class DeleteIntegratedFeatureConsumer(EDAConsumer):

    def consume(self, message: amqp.Message):
        print(f"[DeleteIntegratedFeature] - Consuming a message. Body: {message.body}")
        try:
            body = JSONParser.parse(message.body)
            project_uuid = body.get('project_uuid')
            feature_uuid = body.get('feature_uuid')

            delete_integrated_feature(
                project_uuid=project_uuid,
                feature_uuid=feature_uuid
            )

            message.channel.basic_ack(message.delivery_tag)
            print("[DeleteIntegratedFeature] - IntegratedFeature deleted ")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[DeleteIntegratedFeature] - Message rejected by: {exception}")


class UpdateIntegratedFeatureConsumer(EDAConsumer):

    def consume(self, message: amqp.Message):
        print(f"[UpdateIntegratedFeature] - Consuming a message. Body: {message.body}")
        try:
            body = JSONParser.parse(message.body)
            usecase = UpdateIntegratedFeatureUseCase()
            usecase.update_integrated_feature(body)
            message.channel.basic_ack(message.delivery_tag)
            print("[UpdateIntegratedFeature] - Authorization created: ")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[UpdateIntegratedFeature] - Message rejected by: {exception}")
