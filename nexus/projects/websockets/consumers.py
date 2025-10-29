import json
import logging
import re

from asgiref.sync import async_to_sync
from channels.generic.websocket import WebsocketConsumer
from channels.layers import get_channel_layer

from nexus.projects.exceptions import ProjectDoesNotExist
from nexus.projects.permissions import has_project_permission
from nexus.usecases.projects.projects_use_case import ProjectsUseCase

logger = logging.getLogger(__name__)


def sanitize_user_email(user_email):
    return re.sub("[^A-Za-z0-9]+", "", str(user_email))


def send_message_to_websocket(message):
    channel_layer = get_channel_layer()

    reflection_data = message.messagelog.reflection_data

    object_data = {
        "id": message.messagelog.id,
        "created_at": str(message.created_at),
        "message_text": message.text,
        "tag": reflection_data.get("tag", "failed") if reflection_data else "failed",
        "classification": message.messagelog.classification,
    }

    room_name = f"project_{message.messagelog.project.uuid}"

    async_to_sync(channel_layer.group_send)(
        room_name,
        {
            "type": "chat_message",
            "message": object_data,
            "message_type": "ws",
        },
    )


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
            return

        if not has_project_permission(self.user, self.project, "GET"):
            self.close()
            return

        async_to_sync(self.channel_layer.group_add)(self.room_group_name, self.channel_name)
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
            },
        )

    def chat_message(self, event):
        mtype = {"ping": "pong"}
        message = event["message"]
        message_type = event["message_type"]
        self.send(text_data=json.dumps({"type": mtype.get(message_type, message_type), "message": message}))


class PreviewConsumer(WebsocketConsumer):
    def connect(self):
        try:
            self.user = self.scope["user"]
            self.project_uuid = self.scope["url_route"]["kwargs"]["project"]
            self.room_group_name = f"preview_{self.project_uuid}_{sanitize_user_email(self.user.email)}"
        except (KeyError, TypeError, AttributeError) as e:
            logger.error(f"[ WebsocketError ] {e}")
            self.close()
            return

        try:
            usecases = ProjectsUseCase()
            self.project = usecases.get_by_uuid(self.project_uuid)
        except ProjectDoesNotExist:
            logger.error(f"[ WebsocketError ] {self.project_uuid} Does not Exist")
            self.close()
            return

        if self.user.is_anonymous or self.project is None:
            self.close()
            return

        if not has_project_permission(self.user, self.project, "GET"):
            self.close()
            return

        async_to_sync(self.channel_layer.group_add)(self.room_group_name, self.channel_name)
        self.accept()

    def receive(self, text_data=None, bytes_data=None):
        text_data_json = json.loads(text_data)
        message = text_data_json["message"]
        message_type = text_data_json["type"]

        async_to_sync(self.channel_layer.group_send)(
            self.room_group_name,
            {
                "type": "preview_message",
                "message": message,
                "message_type": message_type,
            },
        )

    def preview_message(self, event):
        mtype = {"ping": "pong"}
        message = event["message"]
        message_type = event["message_type"]
        self.send(text_data=json.dumps({"type": mtype.get(message_type, message_type), "message": message}))


def send_preview_message_to_websocket(project_uuid, message_data, user_email):
    channel_layer = get_channel_layer()
    room_name = f"preview_{project_uuid}_{sanitize_user_email(user_email)}"

    async_to_sync(channel_layer.group_send)(
        room_name,
        {
            "type": "preview_message",
            "message": message_data,
            "message_type": "preview",
        },
    )


async def send_preview_message_to_websocket_async(project_uuid, message_data, user_email):
    """
    Async version of send_preview_message_to_websocket
    """
    channel_layer = get_channel_layer()
    room_name = f"preview_{project_uuid}_{sanitize_user_email(user_email)}"

    await channel_layer.group_send(
        room_name,
        {
            "type": "preview_message",
            "message": message_data,
            "message_type": "preview",
        },
    )
