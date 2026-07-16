from unittest import mock

from django.test import TestCase

from nexus.usecases.intelligences.instructions import (
    build_initial_retail_instruction_payload,
    build_instruction_create_payload,
    resolve_retail_instructions,
)
from nexus.usecases.intelligences.tests.intelligence_factory import ContentBaseFactory, ContentBaseInstructionFactory


class TestResolveRetailInstructions(TestCase):
    @mock.patch("nexus.usecases.intelligences.instructions.settings.DEFAULT_RETAIL_INSTRUCTIONS", ["default one"])
    def test_returns_request_instructions_when_provided(self):
        result = resolve_retail_instructions(["custom one", "custom two"])

        self.assertEqual(result, ["custom one", "custom two"])

    @mock.patch("nexus.usecases.intelligences.instructions.settings.DEFAULT_RETAIL_INSTRUCTIONS", ["default one"])
    def test_returns_settings_when_request_instructions_not_provided(self):
        result = resolve_retail_instructions(None)

        self.assertEqual(result, ["default one"])

    @mock.patch("nexus.usecases.intelligences.instructions.settings.DEFAULT_RETAIL_INSTRUCTIONS", ["default one"])
    def test_returns_empty_list_when_request_instructions_is_empty(self):
        result = resolve_retail_instructions([])

        self.assertEqual(result, [])


class TestBuildInstructionCreatePayload(TestCase):
    def test_builds_instruction_objects(self):
        result = build_instruction_create_payload(["first", "second"])

        self.assertEqual(
            result,
            [{"instruction": "first"}, {"instruction": "second"}],
        )


class TestBuildInitialRetailInstructionPayload(TestCase):
    @mock.patch("nexus.usecases.intelligences.instructions.settings.DEFAULT_RETAIL_INSTRUCTIONS", ["default one"])
    def test_returns_empty_list_when_content_base_already_has_instructions(self):
        content_base = ContentBaseFactory()
        ContentBaseInstructionFactory(content_base=content_base)

        result = build_initial_retail_instruction_payload(content_base, ["custom one"])

        self.assertEqual(result, [])

    @mock.patch("nexus.usecases.intelligences.instructions.settings.DEFAULT_RETAIL_INSTRUCTIONS", ["default one"])
    def test_uses_settings_when_content_base_has_no_instructions(self):
        content_base = ContentBaseFactory()
        content_base.instructions.all().delete()

        result = build_initial_retail_instruction_payload(content_base, None)

        self.assertEqual(result, [{"instruction": "default one"}])

    @mock.patch("nexus.usecases.intelligences.instructions.settings.DEFAULT_RETAIL_INSTRUCTIONS", ["default one"])
    def test_uses_request_instructions_when_content_base_has_no_instructions(self):
        content_base = ContentBaseFactory()
        content_base.instructions.all().delete()

        result = build_initial_retail_instruction_payload(content_base, ["custom one", "custom two"])

        self.assertEqual(
            result,
            [{"instruction": "custom one"}, {"instruction": "custom two"}],
        )
