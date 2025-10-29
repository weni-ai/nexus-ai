from django.db import models


class ZeroshotLogs(models.Model):
    text = models.TextField(help_text="Text to analyze")
    classification = models.TextField()
    other = models.BooleanField()
    options = models.JSONField()
    nlp_log = models.TextField(blank=True)
    created_at = models.DateTimeField("created at", auto_now_add=True)
    language = models.CharField(verbose_name="Language", max_length=64, null=True, blank=True)
    model = models.CharField(verbose_name="Model", max_length=64, default="zeroshot")

    class Meta:
        verbose_name = "zeroshot nlp logs"
        indexes = [models.Index(name="common_zeroshot_log_idx", fields=["nlp_log"])]

    def __str__(self):
        return f"ZeroshotLogs - {self.classification}"
