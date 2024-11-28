from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync


def send_message_to_websocket(message):
    channel_layer = get_channel_layer()

    reflection_data = message.messagelog.reflection_data

    object_data = {
        "id": message.messagelog.id,
        "created_at": str(message.created_at),
        "message_text": message.text,
        "tag": reflection_data.get("tag", "failed") if reflection_data else "failed",
        "classification": message.messagelog.classification
    }

    room_name = f"project_{message.messagelog.project.uuid}"

    async_to_sync(channel_layer.group_send)(
        room_name,
        {
            "type": "chat_message",
            "message": object_data,
            "message_type": "ws",
        }
    )
