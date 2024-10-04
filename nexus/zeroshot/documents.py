import json

from django.conf import settings
from django_elasticsearch_dsl import Document, fields
from django_elasticsearch_dsl.registries import registry

from nexus.zeroshot.models import ZeroshotLogs


@registry.register_document
class ZeroshotLogsDocument(Document):
    class Index:
        name = "zeroshot_logs_nexus"
        settings = {
            'number_of_shards': settings.ELASTICSEARCH_NUMBER_OF_SHARDS,
            'number_of_replicas': settings.ELASTICSEARCH_NUMBER_OF_REPLICAS
        }

    class Django:
        model = ZeroshotLogs
        fields = [
            "text",
            "classification",
            "other",
            "nlp_log",
            "created_at",
            "language"
        ]

    options = fields.TextField()

    def prepare_options(self, instance):
        return json.dumps(instance.options)
