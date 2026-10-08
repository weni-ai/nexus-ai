import json
import tempfile
from pathlib import Path

from django.test import SimpleTestCase, override_settings

from nexus.intelligences.default_instructions import default_instruction_group, default_instruction_texts


class TestDefaultInstructionCatalog(SimpleTestCase):
    def test_unknown_language_uses_portuguese(self):
        texts = default_instruction_texts("klingon")

        self.assertEqual(texts, default_instruction_texts("Portuguese"))
        self.assertIn("NUNCA", texts[1])

    def test_group_marks_every_instruction_as_locked(self):
        group = default_instruction_group("English")

        self.assertFalse(group["editable"])
        self.assertFalse(group["deletable"])
        self.assertEqual(len(group["instructions"]), 7)
        self.assertTrue(all(item["locked"] for item in group["instructions"]))
        self.assertEqual(group["instructions"][0]["id"], "default-1")

    def test_override_file_replaces_only_the_languages_it_defines(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "defaults.json"
            catalog.write_text(json.dumps({"en": ["Custom English rule"]}), encoding="utf-8")

            with override_settings(DEFAULT_PROJECT_INSTRUCTIONS_FILE=str(catalog)):
                english = default_instruction_texts("English")
                portuguese = default_instruction_texts("Portuguese")

        self.assertEqual(english, ["Custom English rule"])
        self.assertEqual(portuguese, default_instruction_texts("pt"))

    def test_invalid_override_file_keeps_the_packaged_catalog(self):
        with tempfile.TemporaryDirectory() as directory:
            catalog = Path(directory) / "defaults.json"
            catalog.write_text("{", encoding="utf-8")

            with override_settings(DEFAULT_PROJECT_INSTRUCTIONS_FILE=str(catalog)):
                texts = default_instruction_texts("Portuguese")

        self.assertIn("NUNCA", texts[1])

    def test_missing_override_file_keeps_the_packaged_catalog(self):
        missing = Path(tempfile.gettempdir()) / "missing-default-instructions.json"

        with override_settings(DEFAULT_PROJECT_INSTRUCTIONS_FILE=str(missing)):
            texts = default_instruction_texts("Spanish")

        self.assertIn("solicita ayuda", texts[0])
