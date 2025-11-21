import amqp
from sentry_sdk import capture_exception

from nexus.event_driven.consumer.consumers import EDAConsumer
from nexus.event_driven.parsers import JSONParser
from nexus.usecases.projects.create import ProjectAuthUseCase


class ProjectAuthConsumer(EDAConsumer):
    def consume(self, message: amqp.Message):
        print(f"[ProjectConsumer] - Consuming a message. Body: {message.body}")
        try:
            body = JSONParser.parse(message.body)

            project_usecase = ProjectAuthUseCase()
            auth = project_usecase.create_project_auth(body)

            message.channel.basic_ack(message.delivery_tag)
            print(f"[ProjectConsumer] - Authorization created: {auth.user.email} - {auth.project.name} - {auth.role}")
        except Exception as exception:
            capture_exception(exception)
            message.channel.basic_reject(message.delivery_tag, requeue=False)
            print(f"[ProjectConsumer] - Message rejected by: {exception}")
