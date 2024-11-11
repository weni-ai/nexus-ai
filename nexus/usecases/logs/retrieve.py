from nexus.logs.models import Message


class RetrieveMessageUseCase:
    def get_by_uuid(self, message_uuid: str):
        return Message.objects.get(uuid=message_uuid)
