from nexus.logs.models import (
    Message,
    MessageLog,
)


class CreateLogUsecase:

    def create_message(self, text: str, contact_urn: str, status: str = "P") -> Message:
        self.message = Message.objects.create(
            text=text,
            contact_urn=contact_urn,
            status=status
        )
        return self.message

    def create_message_log(self, text: str, contact_urn: str, status: str = "P") -> MessageLog:
        message = self.create_message(text, contact_urn, status)
        self.log = MessageLog.objects.create(
            message=message
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

        reflection_data = log.reflection_data or {}
        groundedness_score = kwargs.get("groundedness_score")

        if groundedness_score is not None:
            if groundedness_score < 8:
                reflection_data["tag"] = "Answer not found"
            else:
                reflection_data["tag"] = "Answer found"

        log.reflection_data = reflection_data
        log.save()
