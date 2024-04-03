import amqp
from sentry_sdk import capture_exception

from nexus.projects.project_dto import TriggerConsumerDTO

from nexus.event_driven.parsers import JSONParser
from nexus.event_driven.consumer.consumers import EDAConsumer


class TriggerConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        print(f"[TriggerConsumer] - Consuming a message. Body: {message.body}")
        try:
            body = JSONParser.parse(message.body)

            trigger = TriggerConsumerDTO(
                action=body["action"],
                entity=body["entity"],
                entity_name=body["entity_name"],
                user_email=body["user_email"],
                flow_organization=body["flow_organization"],
                entity_uuid=body["entity_uuid"],  # This is the flow_uuid
                project_uuid=body["project_uuid"],
            )
            # TODO - Implement the logic to handle the trigger, deleting the flow action
            message.channel.basic_ack(message.delivery_tag)
            print(f"[TriggerConsumer] - Trigger readed: {trigger}")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[TriggerConsumer] - Message rejected by: {exception}")
