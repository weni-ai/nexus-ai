from types import SimpleNamespace

from django.test import SimpleTestCase

from router.tasks.invoke import _extract_and_apply_message_context


class ExtractAndApplyMessageContextTestCase(SimpleTestCase):
    def test_strips_context_and_returns_it(self):
        message_obj = SimpleNamespace(text="O café é 100% Arábica?; Context: Product: Café Torrado")
        injected = _extract_and_apply_message_context(message_obj)
        self.assertEqual(message_obj.text, "O café é 100% Arábica?")
        self.assertEqual(injected, "Product: Café Torrado")

    def test_no_delimiter_leaves_text_and_returns_none(self):
        message_obj = SimpleNamespace(text="Hello world")
        injected = _extract_and_apply_message_context(message_obj)
        self.assertEqual(message_obj.text, "Hello world")
        self.assertIsNone(injected)

    def test_empty_text(self):
        message_obj = SimpleNamespace(text="")
        injected = _extract_and_apply_message_context(message_obj)
        self.assertEqual(message_obj.text, "")
        self.assertIsNone(injected)
