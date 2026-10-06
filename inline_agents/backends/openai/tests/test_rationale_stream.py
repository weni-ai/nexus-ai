from unittest.mock import MagicMock

from django.test import SimpleTestCase

from inline_agents.backends.openai.grpc.rationale_stream import RationaleStreamClassifier
from inline_agents.backends.openai.grpc.streaming_client import StreamingSession
from router.clients.flows.http.send_message import FINAL_RESPONSE, RATIONALE


def _session() -> StreamingSession:
    session = StreamingSession(
        stub=MagicMock(),
        msg_id="m1",
        channel_uuid="ch",
        contact_urn="ext:1",
        project_uuid="proj-1",
        metadata={"session_id": "s1", "language": "pt-BR"},
    )
    session._stream_active = True
    return session


class StreamingSessionRationaleTestCase(SimpleTestCase):
    def test_rationale_stays_open_and_merges_session_metadata(self):
        session = _session()

        self.assertTrue(session.send_rationale("Vou consultar o pedido.", "1"))

        message = session._message_queue.get_nowait()
        self.assertEqual(message.type, "rationale")
        self.assertEqual(message.content, "Vou consultar o pedido.")
        self.assertTrue(session.is_active)
        metadata = dict(message.metadata)
        self.assertEqual(metadata["message_kind"], RATIONALE)
        self.assertEqual(metadata["rationale_index"], "1")
        self.assertEqual(metadata["session_id"], "s1")
        self.assertEqual(metadata["language"], "pt-BR")

    def test_delta_and_completed_are_final_response(self):
        session = _session()

        session.send_delta("Não foi ")
        session.send_completed("Não foi possível localizar o pedido.")

        delta = session._message_queue.get_nowait()
        completed = session._message_queue.get_nowait()
        self.assertEqual(delta.type, "delta")
        self.assertEqual(dict(delta.metadata)["message_kind"], FINAL_RESPONSE)
        self.assertEqual(dict(delta.metadata)["language"], "pt-BR")
        self.assertEqual(completed.type, "completed")
        self.assertEqual(dict(completed.metadata)["message_kind"], FINAL_RESPONSE)
        self.assertEqual(completed.content, "Não foi possível localizar o pedido.")
        self.assertFalse(session.is_active)

    def test_blank_rationale_is_not_sent(self):
        session = _session()

        self.assertFalse(session.send_rationale("   ", "1"))
        self.assertTrue(session._message_queue.empty())


class RationaleStreamClassifierTestCase(SimpleTestCase):
    def test_text_then_tool_call_is_one_rationale(self):
        classifier = RationaleStreamClassifier(enabled=True)
        classifier.on_text("Vou ")
        classifier.on_text("consultar o pedido.")
        classifier.on_tool_call()

        pieces = classifier.drain()
        self.assertEqual(len(pieces), 1)
        self.assertEqual(pieces[0].kind, "rationale")
        self.assertEqual(pieces[0].text, "Vou consultar o pedido.")
        self.assertEqual(pieces[0].rationale_index, "1")

    def test_text_without_tool_call_is_released_as_deltas(self):
        classifier = RationaleStreamClassifier(enabled=True)
        classifier.on_text("Não foi ")
        classifier.on_text("possível.")
        classifier.finish()

        pieces = classifier.drain()
        self.assertEqual([(piece.kind, piece.text) for piece in pieces], [("delta", "Não foi "), ("delta", "possível.")])

    def test_empty_hold_emits_no_rationale(self):
        classifier = RationaleStreamClassifier(enabled=True)
        classifier.on_tool_call()
        self.assertEqual(classifier.drain(), [])

    def test_disabled_forwards_deltas_and_ignores_tool_calls(self):
        classifier = RationaleStreamClassifier(enabled=False)
        classifier.on_text("resposta")
        classifier.on_tool_call()
        classifier.finish()

        pieces = classifier.drain()
        self.assertEqual([(piece.kind, piece.text) for piece in pieces], [("delta", "resposta")])

    def test_two_tool_calls_are_indexed_and_a_new_classifier_restarts(self):
        classifier = RationaleStreamClassifier(enabled=True)
        classifier.on_text("Primeiro.")
        classifier.on_tool_call()
        classifier.on_text("Segundo.")
        classifier.on_tool_call()
        classifier.on_text("Resposta.")
        classifier.finish()

        pieces = classifier.drain()
        self.assertEqual(pieces[0].rationale_index, "1")
        self.assertEqual(pieces[1].rationale_index, "2")
        self.assertEqual(pieces[2].kind, "delta")
        self.assertTrue(all(piece.kind != "delta" or piece.text == "Resposta." for piece in pieces))
        self.assertLess(
            next(i for i, piece in enumerate(pieces) if piece.kind == "delta"),
            len(pieces),
        )
        self.assertTrue(all(piece.kind == "rationale" for piece in pieces[:2]))

        restarted = RationaleStreamClassifier(enabled=True)
        restarted.on_text("De novo.")
        restarted.on_tool_call()
        self.assertEqual(restarted.drain()[0].rationale_index, "1")
