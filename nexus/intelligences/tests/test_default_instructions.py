import json
import tempfile
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from nexus.intelligences.default_instructions import (
    DefaultInstructionCatalogError,
    clear_catalog_cache,
    default_instruction_group,
    default_instruction_texts,
)


@override_settings(DEFAULT_PROJECT_INSTRUCTIONS_FILE="")
class TestDefaultInstructionCatalog(SimpleTestCase):
    def setUp(self):
        clear_catalog_cache()

    def test_unknown_language_uses_portuguese(self):
        texts = default_instruction_texts("klingon")

        self.assertEqual(texts, default_instruction_texts("Portuguese"))
        self.assertIn("NUNCA", texts[1])

    def test_regional_locales_use_the_language_prefix(self):
        self.assertEqual(default_instruction_texts("en-US"), default_instruction_texts("English"))
        self.assertEqual(default_instruction_texts("es-MX"), default_instruction_texts("Spanish"))
        self.assertEqual(default_instruction_texts("ro-RO"), default_instruction_texts("Romanian"))
        self.assertEqual(default_instruction_texts("pt_BR"), default_instruction_texts("Portuguese"))

    def test_group_marks_every_instruction_as_locked(self):
        group = default_instruction_group("English")

        self.assertFalse(group["editable"])
        self.assertFalse(group["deletable"])
        self.assertEqual(len(group["instructions"]), 7)
        self.assertTrue(all(item["locked"] for item in group["instructions"]))
        self.assertEqual(group["instructions"][0]["id"], "default-1")

    def test_packaged_catalog_has_the_four_product_languages(self):
        for language in ("Portuguese", "English", "Spanish", "Romanian"):
            self.assertEqual(len(default_instruction_texts(language)), 7)

    def test_override_file_replaces_only_the_languages_it_defines(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "defaults.json"
            catalog.write_text(
                json.dumps(
                    {
                        "en-US": ["Custom English rule"],
                        "fr": ["Ignored"],
                        "es": "not a list",
                        "pt": [],
                    }
                ),
                encoding="utf-8",
            )

            with override_settings(DEFAULT_PROJECT_INSTRUCTIONS_FILE=str(catalog)):
                english = default_instruction_texts("English")
                portuguese = default_instruction_texts("Portuguese")

        self.assertEqual(english, ["Custom English rule"])
        self.assertEqual(portuguese, default_instruction_texts("pt"))

    def test_rereads_the_override_when_the_file_changes(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "defaults.json"
            catalog.write_text(json.dumps({"en": ["First"]}), encoding="utf-8")

            with override_settings(DEFAULT_PROJECT_INSTRUCTIONS_FILE=str(catalog)):
                self.assertEqual(default_instruction_texts("English"), ["First"])
                catalog.write_text(json.dumps({"en": ["Second rule"]}), encoding="utf-8")
                self.assertEqual(default_instruction_texts("English"), ["Second rule"])

    def test_invalid_override_file_keeps_the_packaged_catalog_and_logs_once(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "defaults.json"
            catalog.write_text("{", encoding="utf-8")

            with (
                override_settings(DEFAULT_PROJECT_INSTRUCTIONS_FILE=str(catalog)),
                self.assertLogs("nexus.intelligences.default_instructions", level="WARNING") as logs,
            ):
                first = default_instruction_texts("Portuguese")
                second = default_instruction_texts("Portuguese")

        self.assertIn("NUNCA", first[1])
        self.assertEqual(second, first)
        self.assertEqual(len(logs.output), 1)

    def test_missing_override_file_keeps_the_packaged_catalog(self):
        missing = Path(tempfile.gettempdir()) / "missing-default-instructions.json"

        with override_settings(DEFAULT_PROJECT_INSTRUCTIONS_FILE=str(missing)):
            texts = default_instruction_texts("Spanish")

        self.assertIn("solicita ayuda", texts[0])

    def test_broken_packaged_catalog_raises(self):
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "missing.json"
            with (
                patch("nexus.intelligences.default_instructions._PACKAGED_CATALOG", missing),
                self.assertRaises(DefaultInstructionCatalogError),
            ):
                default_instruction_texts("English")
