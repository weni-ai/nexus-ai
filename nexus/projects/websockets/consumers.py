import json
import logging

from channels.generic.websocket import WebsocketConsumer
from asgiref.sync import async_to_sync

from nexus.usecases.projects.projects_use_case import ProjectsUseCase

from nexus.projects.permissions import has_project_permission
from nexus.projects.exceptions import ProjectDoesNotExist

logger = logging.getLogger(__name__)


class WebsocketMessageConsumer(WebsocketConsumer):
    def connect(self):
        close = False

        try:
            self.user = self.scope["user"]
            self.project_uuid = self.scope["url_route"]["kwargs"]["project"]
            self.room_group_name = f"project_{self.project_uuid}"
        except (KeyError, TypeError, AttributeError) as e:
            logger.error(f"[ WebsocketError ] {e}")
            close = True

        try:
            usecases = ProjectsUseCase()
            self.project = usecases.get_by_uuid(self.project_uuid)
        except ProjectDoesNotExist:
            logger.error(f"[ WebsocketError ] {self.project_uuid} Does not Exist")
            close = True

        if self.user.is_anonymous or close is True or self.project is None:
            self.close()

        if not has_project_permission(
            self.user,
            self.project,
            "GET"
        ):
            self.close()

        async_to_sync(self.channel_layer.group_add)(
            self.room_group_name,
            self.channel_name
        )
        self.accept()

    def receive(self, text_data=None, bytes_data=None):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]
        message_type = text_data_json["type"]

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                "type": "chat_message",
                "message": message,
                "message_type": message_type,
            }
        )

    def chat_message(self, event):
        mtype = {"ping": "pong"}
        message = event["message"]
        message_type = event["message_type"]
        self.send(text_data=json.dumps(
            {"type": mtype.get(message_type, message_type), "message": message}
        ))
