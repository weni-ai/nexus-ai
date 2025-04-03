from django.db import models


class Supervisor(models.Model):
    created_on = models.DateTimeField(auto_now_add=True)
    name = models.CharField(max_length=255)
    instruction = models.TextField()
    foundationModel = models.CharField(max_length=255)
    agentCollaboration = models.CharField(max_length=255)
    promptOverrideConfiguration = models.JSONField()
    memoryConfiguration = models.JSONField()
    actionGroups = models.JSONField()
    knowledgeBases = models.JSONField()
