import amqp
from sentry_sdk import capture_exception

from nexus.projects.project_dto import FlowConsumerDTO

from nexus.event_driven.parsers import JSONParser
from nexus.event_driven.consumer.consumers import EDAConsumer

from nexus.usecases.actions import delete, retrieve


class FlowConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        print(f"[FlowConsumer] - Consuming a message. Body: {message.body}")
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
            print(f"[FlowConsumer] - Flow readed: {flow}")

            try:
                usecase = delete.DeleteFlowsUseCase()
                usecase.hard_delete_flow(flow_dto=dto)
            except retrieve.FlowDoesNotExist:
                print(f"[FlowConsumer] - Flow {flow.entity_name} not found")

        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[FlowConsumer] - Flow rejected by: {exception}")
