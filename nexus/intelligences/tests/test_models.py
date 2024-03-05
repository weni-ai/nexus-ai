import pytest

from nexus.intelligences.models import (
    ContentBaseFile,
    ContentBaseLink,
    ContentBaseText,
    IntegratedIntelligence,
    Intelligence,
    ContentBaseLogs
)


@pytest.mark.django_db
def test_create_intelligence(create_user, create_org):
    org = create_org
    user = create_user
    intel = Intelligence.objects.create(
        name='Test Intelligence', org=org, created_by=user
    )
    assert intel.is_active


@pytest.mark.django_db
def test_create_integrated_intelligence(
    create_user, create_intelligence, create_project
):
    intel = create_intelligence
    project = create_project
    user = create_user
    integrated_intel = IntegratedIntelligence.objects.create(
        project=project, intelligence=intel, created_by=user
    )
    assert integrated_intel


@pytest.mark.django_db
def test_create_content_base_link(
    create_user, create_intelligence, create_content_base
):
    user = create_user
    intel = create_intelligence
    content_base = create_content_base
    content_base = ContentBaseLink.objects.create(
        title='Test content base',
        intelligence=intel,
        created_by=user,
        link='https://test.co',
        content_base=content_base,
    )
    assert content_base.link


@pytest.mark.django_db
def test_create_content_base_file(
    create_user, create_intelligence, create_content_base
):
    user = create_user
    intel = create_intelligence
    file = 'https://test.co'
    content_base = create_content_base

    content_base = ContentBaseFile.objects.create(
        title='Test content base',
        intelligence=intel,
        created_by=user,
        file=file,
        extension_file='txt',
        content_base=content_base,
    )

    assert content_base.file == file
    assert content_base.extension_file == 'txt'


@pytest.mark.django_db
def test_create_content_base_text(
    create_user, create_intelligence, create_content_base
):
    user = create_user
    intel = create_intelligence
    text = 'Lorem Ipsum'
    content_base = create_content_base
    content_base = ContentBaseText.objects.create(
        title='Test content base',
        intelligence=intel,
        created_by=user,
        text=text,
        content_base=content_base,
    )

    assert content_base.text == text


from django.test import TestCase
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFactory


class ContentBaseLogsTestCase(TestCase):
    def setUp(self) -> None:
        self.content_base = ContentBaseFactory()

    def test_create(self):
        log = ContentBaseLogs.objects.create(
            content_base=self.content_base,
            question="",
            language="pt",
            texts_chunks=[""],
            full_prompt="",
            weni_gpt_response="",
            testing=True,
        )
        self.assertIsInstance(log, ContentBaseLogs)

        feedback = 1
        log.update_user_feedback(feedback)

        self.assertEqual(feedback, log.user_feedback)