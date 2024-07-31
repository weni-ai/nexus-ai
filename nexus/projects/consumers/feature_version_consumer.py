import amqp
from sentry_sdk import capture_exception

from nexus.event_driven.parsers import JSONParser
from nexus.event_driven.consumer.consumers import EDAConsumer


class FeatureVersionConsumer(EDAConsumer):

    def consume(self, message: amqp.Message):
        print(f"[FeatureVersion] - Consuming a message. Body: {message.body}")
        try:
            body = JSONParser.parse(message.body)

            message.channel.basic_ack(message.delivery_tag)
            print(f"[FeatureVersionConsumer] - FeatureVersion created: {body.uuid}")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[ProjectConsumer] - Message rejected by: {exception}")
