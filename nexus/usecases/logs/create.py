from nexus.logs.models import (
    Message,
    MessageLog,
)

from django.core.cache import cache


class CreateLogUsecase:

    def _create_redis_cache(
        self,
        message_log: MessageLog,
        project_uuid: str
    ):
        message = message_log.message
        if message.status != "S":
            return

        contact_urn = message.contact_urn
        cache_key = f"last_5_messages_{project_uuid}_{contact_urn}"
        last_5_messages = cache.get(cache_key, [])
        last_5_messages.insert(
            0, {
                "text": message.text,
                "contact_urn": message.contact_urn,
                "llm_respose": message_log.llm_response,
                "project_uuid": project_uuid,
                "content_base_uuid": str(message_log.content_base.uuid),
                "created_at": message.created_at.isoformat(),
                "uuid": str(message.uuid),
                "log_id": message_log.id
            }
        )

        if len(last_5_messages) > 5:
            last_5_messages.pop()

        cache.set(cache_key, last_5_messages)

    def create_message(self, text: str, contact_urn: str, status: str = "P") -> Message:
        self.message = Message.objects.create(
            text=text,
            contact_urn=contact_urn,
            status=status
        )
        return self.message

    def create_message_log(
        self,
        text: str,
        contact_urn: str,
        source: str,
        status: str = "P",
    ) -> MessageLog:

        message = self.create_message(text, contact_urn, status)
        self.log = MessageLog.objects.create(
            message=message,
            source=source
        )
        return self.log

    def update_status(self, status: str, exception_text: str = None):
        update_fields = ["status"]
        message = self.message

        message.status = status
        if exception_text:
            message.exception = exception_text
            update_fields.append("exception")
        message.save(update_fields=update_fields)

        self.message = message
        return self.message

    def update_log_field(self, **kwargs):
        keys = kwargs.keys()
        log = self.log

        for key in keys:
            setattr(log, key, kwargs.get(key))

        log.save()
        if log.project.uuid:
            self._create_redis_cache(log, log.project.uuid)
