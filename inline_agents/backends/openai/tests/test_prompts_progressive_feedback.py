from django.test import SimpleTestCase, override_settings

from inline_agents.backends.openai.adapter import OpenAITeamAdapter
from inline_agents.backends.openai.prompts_progressive_feedback import (
    DEFAULT_PROGRESSIVE_FEEDBACK_ORCHESTRATION_INSTRUCTION,
    inject_progressive_feedback_instruction,
    should_inject_progressive_feedback_instruction,
)

TEST_INSTRUCTION = "Send progressive feedback before tools."
CORE_IDENTITY_XML_PROMPT = "# Manager\n\n" "<core_identity>\n" "You are a customer service leader.\n" "</core_identity>"
CORE_IDENTITY_MARKDOWN_PROMPT = (
    "# Customer Service Assistant\n\n" "## Core Identity\n" "You are a customer service leader."
)
NO_MARKER_PROMPT = "# Manager\n\nYou are a customer service leader."


class TestShouldInjectProgressiveFeedbackInstruction(SimpleTestCase):
    def test_injects_when_rationale_enabled(self):
        self.assertTrue(should_inject_progressive_feedback_instruction(True, False))

    def test_skips_when_rationale_disabled(self):
        self.assertFalse(should_inject_progressive_feedback_instruction(False, False))

    def test_skips_when_turn_off_rationale(self):
        self.assertFalse(should_inject_progressive_feedback_instruction(True, True))


class TestInjectProgressiveFeedbackInstruction(SimpleTestCase):
    def test_injects_before_core_identity_xml_marker(self):
        result = inject_progressive_feedback_instruction(CORE_IDENTITY_XML_PROMPT, TEST_INSTRUCTION)

        self.assertIn(f"{TEST_INSTRUCTION}\n\n<core_identity>", result)
        self.assertLess(result.index(TEST_INSTRUCTION), result.index("<core_identity>"))

    def test_injects_before_core_identity_markdown_marker(self):
        result = inject_progressive_feedback_instruction(CORE_IDENTITY_MARKDOWN_PROMPT, TEST_INSTRUCTION)

        self.assertIn(f"{TEST_INSTRUCTION}\n\n## Core Identity", result)
        self.assertLess(result.index(TEST_INSTRUCTION), result.index("## Core Identity"))

    def test_prepends_when_marker_not_found(self):
        result = inject_progressive_feedback_instruction(NO_MARKER_PROMPT, TEST_INSTRUCTION)

        self.assertTrue(result.startswith(f"{TEST_INSTRUCTION}\n\n# Manager"))

    def test_returns_unchanged_when_instruction_empty(self):
        self.assertEqual(
            inject_progressive_feedback_instruction(CORE_IDENTITY_XML_PROMPT, ""),
            CORE_IDENTITY_XML_PROMPT,
        )


class TestGetSupervisorInstructionsProgressiveFeedback(SimpleTestCase):
    def _call_get_supervisor_instructions(self, **overrides):
        defaults = {
            "instruction": CORE_IDENTITY_XML_PROMPT,
            "date_time_now": "Today is Monday",
            "contact_fields": "",
            "supervisor_name": "Manager",
            "supervisor_role": "Leader",
            "supervisor_goal": "Help customers",
            "supervisor_adjective": "Friendly",
            "supervisor_instructions": "",
            "business_rules": "",
            "project_id": "proj-1",
            "contact_id": "contact-1",
            "contact_name": "Alex",
            "channel_uuid": "channel-1",
            "content_base_uuid": "content-1",
            "use_components": False,
            "use_human_support": False,
            "components_instructions": "",
            "components_instructions_up": "",
            "human_support_instructions": "",
        }
        defaults.update(overrides)
        return OpenAITeamAdapter.get_supervisor_instructions(**defaults)

    @override_settings(PROGRESSIVE_FEEDBACK_ORCHESTRATION_INSTRUCTION=TEST_INSTRUCTION)
    def test_injects_when_rationale_switch_enabled(self):
        result = self._call_get_supervisor_instructions(rationale_switch=True)

        self.assertIn(TEST_INSTRUCTION, result)
        self.assertLess(result.index(TEST_INSTRUCTION), result.index("<core_identity>"))

    @override_settings(PROGRESSIVE_FEEDBACK_ORCHESTRATION_INSTRUCTION=TEST_INSTRUCTION)
    def test_injects_before_markdown_core_identity(self):
        result = self._call_get_supervisor_instructions(
            instruction=CORE_IDENTITY_MARKDOWN_PROMPT,
            rationale_switch=True,
        )

        self.assertIn(TEST_INSTRUCTION, result)
        self.assertLess(result.index(TEST_INSTRUCTION), result.index("## Core Identity"))

    @override_settings(PROGRESSIVE_FEEDBACK_ORCHESTRATION_INSTRUCTION=TEST_INSTRUCTION)
    def test_skips_when_rationale_switch_disabled(self):
        result = self._call_get_supervisor_instructions(rationale_switch=False)

        self.assertNotIn(TEST_INSTRUCTION, result)

    @override_settings(PROGRESSIVE_FEEDBACK_ORCHESTRATION_INSTRUCTION=TEST_INSTRUCTION)
    def test_skips_when_turn_off_rationale(self):
        result = self._call_get_supervisor_instructions(
            rationale_switch=True,
            turn_off_rationale=True,
        )

        self.assertNotIn(TEST_INSTRUCTION, result)

    @override_settings(PROGRESSIVE_FEEDBACK_ORCHESTRATION_INSTRUCTION="")
    def test_skips_when_setting_empty(self):
        result = self._call_get_supervisor_instructions(rationale_switch=True)

        self.assertNotIn(DEFAULT_PROGRESSIVE_FEEDBACK_ORCHESTRATION_INSTRUCTION, result)

    @override_settings(PROGRESSIVE_FEEDBACK_ORCHESTRATION_INSTRUCTION=TEST_INSTRUCTION)
    def test_prepends_when_marker_missing(self):
        result = self._call_get_supervisor_instructions(
            instruction=NO_MARKER_PROMPT,
            rationale_switch=True,
        )

        self.assertTrue(result.startswith(f"{TEST_INSTRUCTION}\n\n# Manager"))
