import amqp
from sentry_sdk import capture_exception

from nexus.event_driven.parsers import JSONParser
from nexus.event_driven.consumer.consumers import EDAConsumer

from nexus.usecases.projects.create import CreateIntegratedFeatureUseCase


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


class CreateIntegratedFeatureFlowConsumer(EDAConsumer):

    def consume(self, message: amqp.Message):
        print(f"[IntegratedFeature] - Consuming a message. Body: {message.body}")
        try:
            body = JSONParser.parse(message.body)

            usecase = CreateIntegratedFeatureUseCase()
            usecase.create_integrated_feature(body)

            message.channel.basic_ack(message.delivery_tag)
            print(f"[IntegratedFeature] - Authorization created: ")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[IntegratedFeature] - Message rejected by: {exception}")


class DeleteIntegratedFeatureConsumer(EDAConsumer):

    def consume(self, message: amqp.Message):
        print(f"[IntegratedFeature] - Consuming a message. Body: {message.body}")
        try:
            body = JSONParser.parse(message.body)
            message.channel.basic_ack(message.delivery_tag)
            print(f"[IntegratedFeature] - Authorization created: ")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[IntegratedFeature] - Message rejected by: {exception}")


class UpdateIntegratedFeatureConsumer(EDAConsumer):

    def consume(self, message: amqp.Message):
        print(f"[IntegratedFeature] - Consuming a message. Body: {message.body}")
        try:
            body = JSONParser.parse(message.body)
            message.channel.basic_ack(message.delivery_tag)
            print(f"[IntegratedFeature] - Authorization created: ")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[IntegratedFeature] - Message rejected by: {exception}")



