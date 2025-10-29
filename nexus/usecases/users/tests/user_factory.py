from uuid import uuid4

import factory

from nexus.users.models import User


class UserFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = User

    language = "en"

    @factory.lazy_attribute
    def email(self):
        return f"test{uuid4().hex}@test.com"
