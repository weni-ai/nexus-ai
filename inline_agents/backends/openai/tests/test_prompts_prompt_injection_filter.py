from django.test import SimpleTestCase, override_settings

from inline_agents.backends.openai.adapter import OpenAITeamAdapter
from inline_agents.backends.openai.prompts_prompt_injection_filter import (
    DEFAULT_PROMPT_INJECTION_FILTER_BLOCK,
    get_prompt_injection_filter_block,
    inject_prompt_injection_filter,
    should_inject_prompt_injection_filter,
)

MANAGER_PROMPT = """<system>
<header>
# Customer Service Assistant
</header>

<core_identity>
You are a customer service leader.
</core_identity>

<scope_boundaries>
## SCOPE BOUNDARIES
</scope_boundaries>
</system>
"""


class PromptInjectionFilterHelpersTestCase(SimpleTestCase):
    def test_should_inject_follows_flag(self):
        self.assertTrue(should_inject_prompt_injection_filter(True))
        self.assertFalse(should_inject_prompt_injection_filter(False))

    def test_inject_after_core_identity_before_scope(self):
        result = inject_prompt_injection_filter(MANAGER_PROMPT, DEFAULT_PROMPT_INJECTION_FILTER_BLOCK)
        core_idx = result.find("</core_identity>")
        safety_idx = result.find("<safety_guardrails>")
        scope_idx = result.find("<scope_boundaries>")
        self.assertNotEqual(safety_idx, -1)
        self.assertLess(core_idx, safety_idx)
        self.assertLess(safety_idx, scope_idx)
        self.assertIn("manipulation_and_injection_defense", result)

    def test_inject_is_idempotent_when_block_already_present(self):
        once = inject_prompt_injection_filter(MANAGER_PROMPT, DEFAULT_PROMPT_INJECTION_FILTER_BLOCK)
        twice = inject_prompt_injection_filter(once, DEFAULT_PROMPT_INJECTION_FILTER_BLOCK)
        self.assertEqual(once.count("<safety_guardrails>"), 1)
        self.assertEqual(twice, once)

    def test_empty_block_noop(self):
        self.assertEqual(inject_prompt_injection_filter(MANAGER_PROMPT, ""), MANAGER_PROMPT)

    @override_settings(GUARDRAILS_PROMPT_INJECTION_FILTER_TEXT="CUSTOM FILTER BLOCK")
    def test_settings_override(self):
        self.assertEqual(get_prompt_injection_filter_block().strip(), "CUSTOM FILTER BLOCK")


class PromptInjectionFilterInSupervisorInstructionsTestCase(SimpleTestCase):
    def _call(self, **overrides):
        defaults = {
            "instruction": MANAGER_PROMPT,
            "date_time_now": "Today",
            "contact_fields": "",
            "supervisor_name": "Manager",
            "supervisor_role": "role",
            "supervisor_goal": "goal",
            "supervisor_adjective": "adj",
            "supervisor_instructions": "",
            "business_rules": "",
            "project_id": "project-uuid",
            "contact_id": "whatsapp:5511999999999",
            "contact_name": "Contact",
            "channel_uuid": "channel-uuid",
            "content_base_uuid": "cb-uuid",
            "use_components": False,
            "use_human_support": False,
            "components_instructions": "",
            "components_instructions_up": "",
            "human_support_instructions": "",
            "rationale_switch": False,
            "prompt_injection_filter_enabled": False,
        }
        defaults.update(overrides)
        return OpenAITeamAdapter.get_supervisor_instructions(**defaults)

    def test_flag_off_does_not_inject(self):
        result = self._call(prompt_injection_filter_enabled=False)
        self.assertNotIn("<safety_guardrails>", result)

    def test_flag_on_injects_block(self):
        result = self._call(prompt_injection_filter_enabled=True)
        self.assertIn("<safety_guardrails>", result)
        self.assertIn("Manipulation & Prompt Injection Defense", result)
        self.assertLess(result.find("</core_identity>"), result.find("<safety_guardrails>"))
        self.assertLess(result.find("<safety_guardrails>"), result.find("<scope_boundaries>"))
