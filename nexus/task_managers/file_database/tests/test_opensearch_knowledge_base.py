from unittest import mock

from django.test import SimpleTestCase, override_settings

from nexus.task_managers.file_database.opensearch_knowledge_base import (
    OpenSearchKnowledgeBaseError,
    _decode_cursor,
    _encode_cursor,
    list_chunks,
)


class TestOpenSearchCursorHelpers(SimpleTestCase):
    def test_encode_decode_cursor_roundtrip(self):
        search_after = ["doc-id-123"]
        cursor = _encode_cursor(search_after)
        self.assertEqual(_decode_cursor(cursor), search_after)

    def test_decode_invalid_cursor_raises(self):
        with self.assertRaises(ValueError):
            _decode_cursor("not-a-valid-cursor")


@override_settings(
    AWS_BEDROCK_KNOWLEDGE_BASE_ID="kb-test",
    AWS_BEDROCK_REGION_NAME="us-east-1",
    AWS_BEDROCK_OPENSEARCH_INDEX_NAME="bedrock-knowledge-base-default-index",
)
class TestListChunks(SimpleTestCase):
    @mock.patch("nexus.task_managers.file_database.opensearch_knowledge_base.get_opensearch_client")
    @mock.patch("nexus.task_managers.file_database.opensearch_knowledge_base.get_opensearch_kb_config")
    def test_list_chunks_returns_paginated_results(self, mock_get_config, mock_get_client):
        mock_get_config.return_value = {
            "host": "test.aoss.amazonaws.com",
            "metadata_field": "AMAZON_BEDROCK_METADATA",
            "text_field": "AMAZON_BEDROCK_TEXT",
            "region": "us-east-1",
            "index_name": "bedrock-knowledge-base-default-index",
        }
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "total": {"value": 2},
                "hits": [
                    {
                        "_id": "doc-1",
                        "sort": ["doc-1"],
                        "_source": {
                            "AMAZON_BEDROCK_TEXT": "hello",
                            "AMAZON_BEDROCK_METADATA": {
                                "contentBaseUuid": "cb-uuid",
                                "filename": "a.pdf",
                                "fileUuid": "file-uuid",
                            },
                        },
                    }
                ],
            }
        }

        result = list_chunks(
            content_base_uuid="cb-uuid",
            data_source_id="ds-uuid",
            page_size=50,
        )

        self.assertEqual(result["count"], 2)
        self.assertEqual(result["page_size"], 50)
        self.assertIsNone(result["next_cursor"])
        self.assertEqual(result["results"][0]["text"], "hello")
        self.assertEqual(result["results"][0]["filename"], "a.pdf")
        self.assertEqual(result["results"][0]["file_uuid"], "file-uuid")

        search_body = mock_client.search.call_args.kwargs["body"]
        self.assertEqual(search_body["size"], 50)
        self.assertEqual(search_body["sort"], [{"_id": "asc"}])
        self.assertNotIn("search_after", search_body)

    @mock.patch("nexus.task_managers.file_database.opensearch_knowledge_base.get_opensearch_client")
    @mock.patch("nexus.task_managers.file_database.opensearch_knowledge_base.get_opensearch_kb_config")
    def test_list_chunks_returns_next_cursor_when_full_page(self, mock_get_config, mock_get_client):
        mock_get_config.return_value = {
            "host": "test.aoss.amazonaws.com",
            "metadata_field": "AMAZON_BEDROCK_METADATA",
            "text_field": "AMAZON_BEDROCK_TEXT",
            "region": "us-east-1",
            "index_name": "bedrock-knowledge-base-default-index",
        }
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "total": {"value": 10},
                "hits": [
                    {
                        "_id": "doc-1",
                        "sort": ["doc-1"],
                        "_source": {
                            "AMAZON_BEDROCK_TEXT": "hello",
                            "AMAZON_BEDROCK_METADATA": {},
                        },
                    }
                ],
            }
        }

        result = list_chunks(
            content_base_uuid="cb-uuid",
            data_source_id="ds-uuid",
            page_size=1,
        )

        self.assertIsNotNone(result["next_cursor"])
        self.assertEqual(_decode_cursor(result["next_cursor"]), ["doc-1"])

    @mock.patch("nexus.task_managers.file_database.opensearch_knowledge_base.get_opensearch_client")
    @mock.patch("nexus.task_managers.file_database.opensearch_knowledge_base.get_opensearch_kb_config")
    def test_list_chunks_passes_search_after_from_cursor(self, mock_get_config, mock_get_client):
        mock_get_config.return_value = {
            "host": "test.aoss.amazonaws.com",
            "metadata_field": "AMAZON_BEDROCK_METADATA",
            "text_field": "AMAZON_BEDROCK_TEXT",
            "region": "us-east-1",
            "index_name": "bedrock-knowledge-base-default-index",
        }
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {"total": {"value": 0}, "hits": []},
        }

        cursor = _encode_cursor(["doc-prev"])
        list_chunks(
            content_base_uuid="cb-uuid",
            data_source_id="ds-uuid",
            page_size=50,
            cursor=cursor,
        )

        search_body = mock_client.search.call_args.kwargs["body"]
        self.assertEqual(search_body["search_after"], ["doc-prev"])

    @mock.patch("nexus.task_managers.file_database.opensearch_knowledge_base.get_opensearch_client")
    @mock.patch("nexus.task_managers.file_database.opensearch_knowledge_base.get_opensearch_kb_config")
    def test_list_chunks_opensearch_failure_raises(self, mock_get_config, mock_get_client):
        mock_get_config.return_value = {
            "host": "test.aoss.amazonaws.com",
            "metadata_field": "AMAZON_BEDROCK_METADATA",
            "text_field": "AMAZON_BEDROCK_TEXT",
            "region": "us-east-1",
            "index_name": "bedrock-knowledge-base-default-index",
        }
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client
        mock_client.search.side_effect = Exception("connection error")

        with self.assertRaises(OpenSearchKnowledgeBaseError):
            list_chunks(
                content_base_uuid="cb-uuid",
                data_source_id="ds-uuid",
                page_size=50,
            )
