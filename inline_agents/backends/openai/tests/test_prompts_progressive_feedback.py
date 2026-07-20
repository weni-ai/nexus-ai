from django.test import SimpleTestCase, override_settings

from inline_agents.backends.openai.adapter import OpenAITeamAdapter
from inline_agents.backends.openai.prompts_progressive_feedback import (
    DEFAULT_PROGRESSIVE_FEEDBACK_ORCHESTRATION_INSTRUCTION,
    find_core_identity_marker,
    inject_progressive_feedback_instruction,
    should_inject_progressive_feedback_instruction,
)
from router.traces_observers.rationale.channel_hint import (
    channel_hint_from_contact_urn,
    is_webchat_channel,
    supports_progressive_feedback,
)

TEST_INSTRUCTION = "Send progressive feedback before tools."
WEBCHAT_CONTACT_URN = "project-abc-session-ext:212034573131@webchat.ai.test"
AMERICANAS_WEBCHAT_CONTACT_URN = "ext:1486635309559@www.americanas.com.br"
WHATSAPP_CONTACT_URN = "whatsapp:5511999999999"
CORE_IDENTITY_XML_PROMPT = "# Manager\n\n" "<core_identity>\n" "You are a customer service leader.\n" "</core_identity>"
CORE_IDENTITY_MARKDOWN_PROMPT = (
    "# Customer Service Assistant\n\n" "## Core Identity\n" "You are a customer service leader."
)
NO_MARKER_PROMPT = "# Manager\n\nYou are a customer service leader."


class TestChannelHintFromContactUrn(SimpleTestCase):
    def test_webchat_ext_urn(self):
        self.assertEqual(channel_hint_from_contact_urn(AMERICANAS_WEBCHAT_CONTACT_URN), "web")

    def test_webchat_domain_urn(self):
        self.assertEqual(channel_hint_from_contact_urn(WEBCHAT_CONTACT_URN), "web")

    def test_non_webchat_urn_uses_prefix(self):
        self.assertEqual(channel_hint_from_contact_urn(WHATSAPP_CONTACT_URN), "whatsapp")

    def test_unknown_when_empty(self):
        self.assertEqual(channel_hint_from_contact_urn(""), "unknown")


class TestSupportsProgressiveFeedback(SimpleTestCase):
    def test_americanas_webchat_urn_supported(self):
        self.assertTrue(supports_progressive_feedback(AMERICANAS_WEBCHAT_CONTACT_URN))

    def test_webchat_urn_supported(self):
        self.assertTrue(supports_progressive_feedback(WEBCHAT_CONTACT_URN))

    def test_wwc_channel_type_supported(self):
        self.assertTrue(supports_progressive_feedback("contact-1", "WWC"))

    def test_non_webchat_not_supported(self):
        self.assertFalse(supports_progressive_feedback(WHATSAPP_CONTACT_URN))

    def test_preview_bypasses_channel_restriction(self):
        self.assertTrue(supports_progressive_feedback(WHATSAPP_CONTACT_URN, preview=True))

    def test_is_webchat_channel(self):
        self.assertTrue(is_webchat_channel(AMERICANAS_WEBCHAT_CONTACT_URN))
        self.assertFalse(is_webchat_channel(WHATSAPP_CONTACT_URN))


class TestFindCoreIdentityMarker(SimpleTestCase):
    def test_finds_xml_marker(self):
        self.assertEqual(find_core_identity_marker(CORE_IDENTITY_XML_PROMPT), "<core_identity>")

    def test_finds_markdown_marker(self):
        self.assertEqual(find_core_identity_marker(CORE_IDENTITY_MARKDOWN_PROMPT), "## Core Identity")

    def test_returns_none_when_marker_missing(self):
        self.assertIsNone(find_core_identity_marker(NO_MARKER_PROMPT))


class TestShouldInjectProgressiveFeedbackInstruction(SimpleTestCase):
    def test_injects_when_rationale_enabled_on_webchat(self):
        self.assertTrue(
            should_inject_progressive_feedback_instruction(
                True,
                False,
                contact_urn=WEBCHAT_CONTACT_URN,
            )
        )

    def test_skips_on_non_webchat(self):
        self.assertFalse(
            should_inject_progressive_feedback_instruction(
                True,
                False,
                contact_urn=WHATSAPP_CONTACT_URN,
            )
        )

    def test_skips_when_rationale_disabled(self):
        self.assertFalse(
            should_inject_progressive_feedback_instruction(
                False,
                False,
                contact_urn=WEBCHAT_CONTACT_URN,
            )
        )

    def test_skips_when_turn_off_rationale(self):
        self.assertFalse(
            should_inject_progressive_feedback_instruction(
                True,
                True,
                contact_urn=WEBCHAT_CONTACT_URN,
            )
        )


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
            "contact_id": WEBCHAT_CONTACT_URN,
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
    def test_injects_for_americanas_webchat_urn(self):
        result = self._call_get_supervisor_instructions(
            rationale_switch=True,
            contact_id=AMERICANAS_WEBCHAT_CONTACT_URN,
        )

        self.assertIn(TEST_INSTRUCTION, result)

    @override_settings(PROGRESSIVE_FEEDBACK_ORCHESTRATION_INSTRUCTION=TEST_INSTRUCTION)
    def test_skips_on_non_webchat(self):
        result = self._call_get_supervisor_instructions(
            rationale_switch=True,
            contact_id=WHATSAPP_CONTACT_URN,
        )

        self.assertNotIn(TEST_INSTRUCTION, result)

    @override_settings(PROGRESSIVE_FEEDBACK_ORCHESTRATION_INSTRUCTION=TEST_INSTRUCTION)
    def test_prepends_when_marker_missing(self):
        result = self._call_get_supervisor_instructions(
            instruction=NO_MARKER_PROMPT,
            rationale_switch=True,
        )

        self.assertTrue(result.startswith(f"{TEST_INSTRUCTION}\n\n# Manager"))
