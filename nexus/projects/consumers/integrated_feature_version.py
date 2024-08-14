import amqp
from sentry_sdk import capture_exception

from nexus.event_driven.parsers import JSONParser
from nexus.event_driven.consumer.consumers import EDAConsumer

from nexus.usecases.projects.create import CreateIntegratedFeatureVersionUseCase
from nexus.usecases.projects.dto import IntegratedFeatureVersionDTO


class IntegratedFeatureVersionConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        print(f"[IntegratedFeatureVersionConsumer] - Consuming a message. Body: {message.body}")
        body = JSONParser.parse(message.body)
        integrated_feature_version_dto = IntegratedFeatureVersionDTO(**body)
        try:
            CreateIntegratedFeatureVersionUseCase().create(integrated_feature_version_dto)
            message.channel.basic_ack(message.delivery_tag)
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[IntegratedFeatureVersionConsumer] - Message rejected by: {exception}")
