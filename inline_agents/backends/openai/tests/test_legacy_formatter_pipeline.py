"""Tests for legacy pipeline version helpers."""

from django.test import SimpleTestCase

from inline_agents.backends.openai.legacy_formatter_pipeline import (
    LEGACY_PIPELINE_VERSION,
    is_legacy_pipeline_version,
    normalize_pipeline_version,
    use_legacy_formatter_after_manager,
)


class LegacyFormatterPipelineTest(SimpleTestCase):
    def test_legacy_token(self):
        self.assertTrue(is_legacy_pipeline_version("2.6"))
        self.assertTrue(use_legacy_formatter_after_manager("2.6"))

    def test_strip_whitespace(self):
        self.assertTrue(is_legacy_pipeline_version("  2.6 \n"))

    def test_non_legacy(self):
        self.assertFalse(is_legacy_pipeline_version(None))
        self.assertFalse(is_legacy_pipeline_version(""))
        self.assertFalse(is_legacy_pipeline_version("2.7"))
        self.assertFalse(use_legacy_formatter_after_manager("2.7"))

    def test_normalize(self):
        self.assertIsNone(normalize_pipeline_version(None))
        self.assertEqual(normalize_pipeline_version("  x "), "x")

    def test_constant(self):
        self.assertEqual(LEGACY_PIPELINE_VERSION, "2.6")
