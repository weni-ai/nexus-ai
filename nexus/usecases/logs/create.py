from nexus.logs.models import Message, MessageLog


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
            print(log, key, kwargs.get(key))
            setattr(log, key, kwargs.get(key))

        log.save()

        


# message = models.OneToOneField(Message, on_delete=models.CASCADE)
# chunks = ArrayField(models.TextField())
# prompt = models.TextField()
# project = models.ForeignKey(Project, on_delete=models.CASCADE)
# content_base = models.ForeignKey(ContentBase, on_delete=models.CASCADE)
# classification = models.CharField(max_length=255)
# llm_model = models.CharField(max_length=255)
# llm_response = models.TextField()
# created_at = models.DateTimeField(auto_now_add=True)
# metadata = models.JSONField()

# class Teste:
#     def update_log_field(self, **kwargs):
#         print(kwargs)

# Teste().update_log_field(nome="adlkasd", contato=1232312)