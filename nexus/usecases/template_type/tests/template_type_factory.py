import json
import factory
from uuid import uuid4


from nexus.projects.models import TemplateType


class TemplateTypeFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TemplateType

    name = factory.sequence(lambda o: f"TemplateType {o}")
    uuid = str(uuid4())
    setup = json.dumps({"key": "value"})
