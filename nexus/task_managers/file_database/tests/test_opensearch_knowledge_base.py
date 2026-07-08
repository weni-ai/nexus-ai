from unittest import mock

from django.test import SimpleTestCase, override_settings

from nexus.task_managers.file_database.opensearch_knowledge_base import (
    OpenSearchKnowledgeBaseError,
    _build_chunk_filters,
    _decode_cursor,
    _encode_cursor,
    _format_chunk,
    list_chunks,
)

SAMPLE_HIT = {
    "_id": "1%3A0%3AUGqQ3pIBAKgip1x7S2L1",
    "_source": {
        "x-amz-bedrock-kb-source-uri": (
            "s3://develop-bucket/69a11794-c405-4331-adff-0894265f1c47/"
            "3b2c492a-bf66-46d2-81e0-bf38c791bb1c-55c7e6df-a6e1-42d3-ab72-7c43922286a2.md"
        ),
        "AMAZON_BEDROCK_METADATA": "{'source':'s3://develop-bucket/example.md'}",
        "x-amz-bedrock-kb-data-source-id": "U9EWWYEYCT",
        "AMAZON_BEDROCK_TEXT_CHUNK": "chunk text",
        "fileUuid": "3b2c492a-bf66-46d2-81e0-bf38c791bb1c",
        "contentBaseUuid": "69a11794-c405-4331-adff-0894265f1c47",
    },
}


class TestOpenSearchCursorHelpers(SimpleTestCase):
    def test_build_chunk_filters_uses_top_level_fields(self):
        filters = _build_chunk_filters("69a11794-c405-4331-adff-0894265f1c47", "U9EWWYEYCT")
        self.assertEqual(
            filters,
            [
                {"term": {"contentBaseUuid.keyword": "69a11794-c405-4331-adff-0894265f1c47"}},
                {"term": {"x-amz-bedrock-kb-data-source-id.keyword": "U9EWWYEYCT"}},
            ],
        )

    def test_format_chunk_reads_top_level_bedrock_document(self):
        chunk = _format_chunk(
            SAMPLE_HIT,
            text_field="AMAZON_BEDROCK_TEXT_CHUNK",
            metadata_field="AMAZON_BEDROCK_METADATA",
        )

        self.assertEqual(chunk["text"], "chunk text")
        self.assertEqual(chunk["file_uuid"], "3b2c492a-bf66-46d2-81e0-bf38c791bb1c")
        self.assertEqual(
            chunk["filename"],
            "3b2c492a-bf66-46d2-81e0-bf38c791bb1c-55c7e6df-a6e1-42d3-ab72-7c43922286a2.md",
        )
        self.assertEqual(chunk["metadata"]["contentBaseUuid"], "69a11794-c405-4331-adff-0894265f1c47")

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
            "text_field": "AMAZON_BEDROCK_TEXT_CHUNK",
            "region": "us-east-1",
            "index_name": "bedrock-knowledge-base-default-index",
        }
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "total": {"value": 2},
                "hits": [{**SAMPLE_HIT, "sort": ["doc-1"]}],
            }
        }

        result = list_chunks(
            content_base_uuid="69a11794-c405-4331-adff-0894265f1c47",
            data_source_id="U9EWWYEYCT",
            page_size=50,
        )

        self.assertEqual(result["count"], 2)
        self.assertEqual(result["page_size"], 50)
        self.assertIsNone(result["next_cursor"])
        self.assertEqual(result["results"][0]["text"], "chunk text")
        self.assertEqual(result["results"][0]["file_uuid"], "3b2c492a-bf66-46d2-81e0-bf38c791bb1c")

        search_body = mock_client.search.call_args.kwargs["body"]
        self.assertEqual(search_body["size"], 50)
        self.assertEqual(search_body["sort"], [{"_id": "asc"}])
        self.assertEqual(
            search_body["query"]["bool"]["filter"],
            [
                {"term": {"contentBaseUuid.keyword": "69a11794-c405-4331-adff-0894265f1c47"}},
                {"term": {"x-amz-bedrock-kb-data-source-id.keyword": "U9EWWYEYCT"}},
            ],
        )
        self.assertNotIn("search_after", search_body)

    @mock.patch("nexus.task_managers.file_database.opensearch_knowledge_base.get_opensearch_client")
    @mock.patch("nexus.task_managers.file_database.opensearch_knowledge_base.get_opensearch_kb_config")
    def test_list_chunks_returns_next_cursor_when_full_page(self, mock_get_config, mock_get_client):
        mock_get_config.return_value = {
            "host": "test.aoss.amazonaws.com",
            "metadata_field": "AMAZON_BEDROCK_METADATA",
            "text_field": "AMAZON_BEDROCK_TEXT_CHUNK",
            "region": "us-east-1",
            "index_name": "bedrock-knowledge-base-default-index",
        }
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client
        mock_client.search.return_value = {
            "hits": {
                "total": {"value": 10},
                "hits": [{**SAMPLE_HIT, "sort": ["doc-1"]}],
            }
        }

        result = list_chunks(
            content_base_uuid="69a11794-c405-4331-adff-0894265f1c47",
            data_source_id="U9EWWYEYCT",
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
            "text_field": "AMAZON_BEDROCK_TEXT_CHUNK",
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
            content_base_uuid="69a11794-c405-4331-adff-0894265f1c47",
            data_source_id="U9EWWYEYCT",
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
            "text_field": "AMAZON_BEDROCK_TEXT_CHUNK",
            "region": "us-east-1",
            "index_name": "bedrock-knowledge-base-default-index",
        }
        mock_client = mock.Mock()
        mock_get_client.return_value = mock_client
        mock_client.search.side_effect = Exception("connection error")

        with self.assertRaises(OpenSearchKnowledgeBaseError):
            list_chunks(
                content_base_uuid="69a11794-c405-4331-adff-0894265f1c47",
                data_source_id="U9EWWYEYCT",
                page_size=50,
            )
