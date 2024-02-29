import factory

from nexus.usecases.users.tests.user_factory import UserFactory
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFileFactory, ContentBaseTextFactory
from nexus.task_managers.models import ContentBaseFileTaskManager, ContentBaseTextTaskManager


class ContentBaseFileTaskManagerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBaseFileTaskManager

    status = ContentBaseFileTaskManager.STATUS_PROCESSING
    created_by = factory.SubFactory(UserFactory)
    content_base_file = factory.SubFactory(
        ContentBaseFileFactory,
        created_by=factory.SelfAttribute("..created_by"),
    )


class ContentBaseTextTaskManagerFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = ContentBaseTextTaskManager

    status = ContentBaseTextTaskManager.STATUS_PROCESSING
    created_by = factory.SubFactory(UserFactory)
    content_base_text = factory.SubFactory(
        ContentBaseTextFactory,
        created_by=factory.SelfAttribute("..created_by"),
    )
    file_url = "http://test.com"
    file_name = "test.txt"
