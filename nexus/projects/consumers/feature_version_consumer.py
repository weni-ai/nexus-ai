import amqp
from sentry_sdk import capture_exception

from nexus.event_driven.parsers import JSONParser
from nexus.event_driven.consumer.consumers import EDAConsumer


msg_example = {
    "feature_version_uuid": "10cc12f6-21ec-45b0-b983-532efe59a657",
    "uuid": "10cc12f6-21ec-45b0-b983-532efe59a658",
    "brain": {
        "name": "Teste",
        "ocupation": "especialista em testes",
        "personality": "amigavel",
        "objective": "tirar duvidas sobre testes",
        "instructions": [
            "não falar palavrão",
            "não fazer piada"
        ],
        "actions": [
            {
                "flow_uuid": "",
                "name": "teste", # nome da ação e não necessariamente do fluxo
                "description": "essa é uma descrição"
            }
        ]
    }
}



class FeatureVersionConsumer(EDAConsumer):

    def consume(self, message: amqp.Message):
        print(f"[FeatureVersion] - Consuming a message. Body: {message.body}")
        try:
            body = JSONParser.parse(message.body)

            message.channel.basic_ack(message.delivery_tag)
            print(f"[FeatureVersionConsumer] - FeatureVersion created: {project_dto.uuid}")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[ProjectConsumer] - Message rejected by: {exception}")
