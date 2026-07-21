from django.test import SimpleTestCase

from router.traces_observers.rationale.context import RationaleContext, TraceData


class TestTraceDataShapes(SimpleTestCase):
    def test_bedrock_flat_orchestration_under_trace(self):
        payload = {
            "trace": {
                "orchestrationTrace": {
                    "rationale": {"text": "checking cep", "reasoningId": "r1"},
                }
            }
        }
        td = TraceData(payload)
        self.assertEqual(td.get_rationale_text(), "checking cep")
        self.assertFalse(td.has_called_agent())

    def test_openai_thinking_nested_trace(self):
        payload = {
            "config": {"type": "thinking"},
            "trace": {
                "collaboratorName": "",
                "eventTime": "now",
                "trace": {
                    "orchestrationTrace": {
                        "rationale": {
                            "text": "Vou verificar o CEP",
                            "reasoningId": "message_interim_fallback",
                        }
                    }
                },
            },
        }
        td = TraceData(payload)
        self.assertEqual(td.get_rationale_text(), "Vou verificar o CEP")
        self.assertFalse(td.has_called_agent())

    def test_openai_agent_start_has_called_agent(self):
        payload = {
            "config": {"type": "delegating_to_agent"},
            "trace": {
                "orchestrationTrace": {
                    "invocationInput": {
                        "agentCollaboratorInvocationInput": {
                            "agentCollaboratorName": "utility_agent",
                        },
                        "invocationType": "AGENT_COLLABORATOR",
                    }
                }
            },
        }
        td = TraceData(payload)
        self.assertIsNone(td.get_rationale_text())
        self.assertTrue(td.has_called_agent())


class TestRationaleContextFromKwargs(SimpleTestCase):
    def test_accepts_msg_external_id_alias(self):
        ctx = RationaleContext.from_kwargs(
            session_id="s1",
            msg_external_id="ext-1",
            preview_websocket=True,
        )
        self.assertEqual(ctx.message_external_id, "ext-1")
        self.assertTrue(ctx.preview_websocket)
