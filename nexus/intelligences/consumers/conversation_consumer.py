import amqp
from sentry_sdk import capture_exception

from nexus.intelligences.conversation_dto import WindowConversationDTO

from nexus.event_driven.parsers import JSONParser
from nexus.event_driven.consumer.consumers import EDAConsumer
from nexus.usecases.intelligences.lambda_usecase import LambdaUseCase

class  ConversationConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        print(f"[ ConversationConsumer ] - Consuming a message. Body: {message.body}")
        try:
            body = JSONParser.parse(message.body)

            window_conversation_dto = WindowConversationDTO(
                project_uuid=body.get("project_uuid"),
                channel_uuid=body.get("channel_uuid"),
                start_date=body.get("start"),
                end_date=body.get("end"),
                contact_urn=body.get("contact_urn"),
                has_chats_room=body.get("has_chats_room"),
            )

            # TODO: call lambda functions to get the conversation resolution and the topics of the conversation
            lambda_use_case = LambdaUseCase()
            lambda_use_case.invoke_lambda(
                lambda_name="conversation-resolution",
                payload=window_conversation_dto.dict() # set conversation payload
            )

            lambda_use_case.invoke_lambda(
                lambda_name="conversation-topics",
                payload=window_conversation_dto.dict() # set topics payload
            )

            message.channel.basic_ack(message.delivery_tag)
            print(f"[ ConversationConsumer ] - get conversation: {window_conversation_dto.contact_urn} {window_conversation_dto.start_date} - {window_conversation_dto.end_date}")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[ ConversationConsumer ] - Message rejected by: {exception}")
