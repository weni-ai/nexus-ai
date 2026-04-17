"""Extra supervisor instructions when using streaming component tools + merge (no formatter LLM)."""

# Appended to rendered components_instructions / components_instructions_up when use_components is True.

PROMPT_SUPERVISOR_COMPONENTS_UP = """
## Interactive components (streaming)
You have tools for quick replies, list pickers, and CTA buttons. Call the appropriate tool when the reply
should include those UI elements. After calling a tool, continue the assistant message in natural language
as needed; the channel will merge your text with the structured component data automatically.
Do not repeat raw JSON for components in plain text after using a component tool.
"""

PROMPT_SUPERVISOR_COMPONENTS = """
## Component tool usage
- Use create_quick_replies_message when the user should pick from 2–3 short options (no descriptions).
- Use create_list_message for longer menus, descriptions, or four or more options.
- Use create_cta_message when there is exactly one primary URL to open.
- For plain informational answers without interactive UI, answer normally without those tools.
- For catalogs, products with SKUs, or combined templates, use the dedicated catalog or combined tools as usual.
"""
