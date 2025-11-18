import pytest
from django.core.exceptions import ValidationError
from django.test import TestCase

from nexus.intelligences.models import (
    ContentBaseFile,
    ContentBaseLink,
    ContentBaseLogs,
    ContentBaseText,
    IntegratedIntelligence,
    Intelligence,
)
from nexus.usecases.intelligences.tests.intelligence_factory import (
    ContentBaseFactory,
    IntegratedIntelligenceFactory,
    IntelligenceFactory,
)


@pytest.mark.django_db
def test_create_intelligence(create_user, create_org):
    org = create_org
    user = create_user
    intel = Intelligence.objects.create(name="Test Intelligence", org=org, created_by=user)
    assert intel.is_active


@pytest.mark.django_db
def test_create_integrated_intelligence(create_user, create_intelligence, create_project):
    intel = create_intelligence
    project = create_project
    user = create_user
    integrated_intel = IntegratedIntelligence.objects.create(project=project, intelligence=intel, created_by=user)
    assert integrated_intel


@pytest.mark.django_db
def test_create_content_base_link(create_user, create_intelligence, create_content_base):
    user = create_user
    content_base = create_content_base
    content_base_link = ContentBaseLink.objects.create(
        link="https://test.co",
        content_base=content_base,
        created_by=user,
    )
    assert content_base_link.link


@pytest.mark.django_db
def test_create_content_base_file(create_user, create_intelligence, create_content_base):
    user = create_user
    file = "https://test.co"
    content_base = create_content_base

    content_base_file = ContentBaseFile.objects.create(
        file=file,
        extension_file="txt",
        content_base=content_base,
        created_by=user,
    )

    assert content_base_file.file == file
    assert content_base_file.extension_file == "txt"


@pytest.mark.django_db
def test_create_content_base_text(create_user, create_intelligence, create_content_base):
    user = create_user
    text = "Lorem Ipsum"
    content_base = create_content_base
    content_base_text = ContentBaseText.objects.create(
        text=text,
        content_base=content_base,
        created_by=user,
    )

    assert content_base_text.text == text


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
        log.update_user_feedback(correct_answer=True, feedback=feedback)

        self.assertEqual(feedback, log.user_feedback)


class IntegratedIntelligenceTestCase(TestCase):
    def setUp(self) -> None:
        self.content_base = ContentBaseFactory(is_router=True)
        # Make sure the intelligence is also a router
        self.content_base.intelligence.is_router = True
        self.content_base.intelligence.save()

        self.integrated_intelligence = IntegratedIntelligenceFactory(intelligence=self.content_base.intelligence)
        self.project = self.integrated_intelligence.project

    def test_multiple_integrated_routers(self):
        # Create a second intelligence that is a router
        intelligence_2 = IntelligenceFactory(is_router=True)
        with self.assertRaises(ValidationError):
            IntegratedIntelligence.objects.create(
                project=self.project, intelligence=intelligence_2, created_by=self.integrated_intelligence.created_by
            )
