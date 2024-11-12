from nexus.logs.models import MessageLog


class RetrieveMessageLogUseCase:
    def get_by_id(self, message_uuid: str):
        return MessageLog.objects.get(id=message_uuid)
