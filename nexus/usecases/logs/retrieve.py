from nexus.logs.models import MessageLog


class RetrieveMessageLogUseCase:
    def get_by_id(self, log_id: str):
        return MessageLog.objects.get(id=log_id)
