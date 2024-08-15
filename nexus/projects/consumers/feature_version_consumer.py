import amqp
from sentry_sdk import capture_exception

from nexus.projects.models import FeatureVersion

from nexus.event_driven.parsers import JSONParser
from nexus.event_driven.consumer.consumers import EDAConsumer

from nexus.usecases.projects.create import CreateFeatureVersionUseCase
from nexus.usecases.projects.update import UpdateFeatureVersionUseCase


class FeatureVersionConsumer(EDAConsumer):

    def consume(self, message: amqp.Message):
        print(f"[FeatureVersion] - Consuming a message. Body: {message.body}")
        try:
            body = JSONParser.parse(message.body)
            feature_version = FeatureVersion.objects.filter(uuid=body.get('uuid'))

            if feature_version.exists():
                usecase = UpdateFeatureVersionUseCase()
                usecase.update_feature_version(consumer_msg=body)

                message.channel.basic_ack(message.delivery_tag)
                print(f"[FeatureVersionConsumer] - FeatureVersion updated: {body.get('uuid')}")
            else:
                usecase = CreateFeatureVersionUseCase()
                created = usecase.create_feature_version(consumer_msg=body)

                if created:
                    message.channel.basic_ack(message.delivery_tag)
                    print(f"[FeatureVersionConsumer] - FeatureVersion created: {body.get('uuid')}")
                else:
                    message.channel.basic_reject(message.delivery_tag, requeue=False)
                    print(f"[FeatureVersionConsumer] - Message rejected by: {body.get('uuid')}")

        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[FeatureVersionConsumer] - Message rejected by: {exception}")
