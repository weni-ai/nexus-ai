from unittest import TestCase

from router.tasks.message_external_id import enrich_message_msg_external_id, resolve_msg_external_id


class ResolveMsgExternalIdTestCase(TestCase):
    def test_prefers_msg_external_id(self):
        message = {"msg_event": {"msg_external_id": "flows-id-1", "msg_uuid": "uuid-2"}}
        self.assertEqual(resolve_msg_external_id(message), "flows-id-1")

    def test_falls_back_to_msg_uuid(self):
        message = {"msg_event": {"msg_uuid": "2e619008-915d-4a03-8a95-5cc606234a2e"}}
        self.assertEqual(resolve_msg_external_id(message), "2e619008-915d-4a03-8a95-5cc606234a2e")

    def test_falls_back_to_msg_id(self):
        message = {"msg_event": {"msg_id": 268504096}}
        self.assertEqual(resolve_msg_external_id(message), "268504096")

    def test_falls_back_to_metadata_msg_uuid(self):
        message = {"msg_event": {}, "metadata": {"msg_uuid": "meta-uuid-9"}}
        self.assertEqual(resolve_msg_external_id(message), "meta-uuid-9")

    def test_returns_empty_when_missing(self):
        self.assertEqual(resolve_msg_external_id({}), "")
        self.assertEqual(resolve_msg_external_id({"msg_event": {}}), "")

    def test_enrich_sets_msg_external_id_from_msg_uuid(self):
        enriched = enrich_message_msg_external_id({"msg_event": {"msg_uuid": "abc-123"}})
        self.assertEqual(enriched["msg_event"]["msg_external_id"], "abc-123")

    def test_enrich_preserves_existing_msg_external_id(self):
        enriched = enrich_message_msg_external_id({"msg_event": {"msg_external_id": "keep-me", "msg_uuid": "other"}})
        self.assertEqual(enriched["msg_event"]["msg_external_id"], "keep-me")
