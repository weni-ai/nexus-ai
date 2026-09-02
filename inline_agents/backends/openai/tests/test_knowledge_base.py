from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase, override_settings

from inline_agents.backends.openai.entities import HooksState
from inline_agents.backends.openai.knowledge_base import (
    NO_KNOWLEDGE_BASE_RESPONSE,
    consume_knowledge_base_retrieved_references,
    format_knowledge_base_retrieval_results,
    retrieve_knowledge_base,
)


class FormatKnowledgeBaseRetrievalResultsTests(SimpleTestCase):
    def test_includes_filename_and_file_uuid_without_s3_uri(self):
        retrieval_results = [
            {
                "content": {"text": "Shipping is free over 100."},
                "metadata": {
                    "x-amz-bedrock-kb-source-uri": "s3://internal-bucket/file.docx",
                    "filename": "policy.docx",
                    "fileUuid": "file-uuid-1",
                    "x-amz-bedrock-kb-data-source-id": "ds-1",
                    "contentBaseUuid": "cb-1",
                },
            }
        ]

        text, references = format_knowledge_base_retrieval_results(retrieval_results)

        self.assertEqual(text, "Shipping is free over 100.")
        self.assertEqual(
            references,
            [
                {
                    "text": "Shipping is free over 100.",
                    "filename": "policy.docx",
                    "fileUuid": "file-uuid-1",
                }
            ],
        )
        self.assertNotIn("x-amz-bedrock-kb-source-uri", references[0])

    def test_omits_missing_metadata_without_failing(self):
        retrieval_results = [
            {"content": {"text": "Chunk without filename"}},
            {"content": {"text": "Chunk with name"}, "metadata": {"filename": "guide.pdf"}},
        ]

        text, references = format_knowledge_base_retrieval_results(retrieval_results)

        self.assertEqual(text, "Chunk without filename\nChunk with name")
        self.assertEqual(
            references,
            [
                {"text": "Chunk without filename"},
                {"text": "Chunk with name", "filename": "guide.pdf"},
            ],
        )

    def test_empty_results_returns_fallback_text(self):
        text, references = format_knowledge_base_retrieval_results([])
        self.assertEqual(text, NO_KNOWLEDGE_BASE_RESPONSE)
        self.assertEqual(references, [])


class ConsumeKnowledgeBaseRetrievedReferencesTests(SimpleTestCase):
    def test_returns_pending_references_and_clears_state(self):
        hooks_state = HooksState(agents=[])
        pending = [{"text": "chunk", "filename": "a.docx"}]
        hooks_state.knowledge_base_retrieved_references = pending

        consumed = consume_knowledge_base_retrieved_references(hooks_state)

        self.assertEqual(consumed, pending)
        self.assertIsNone(hooks_state.knowledge_base_retrieved_references)

    def test_falls_back_to_empty_list(self):
        hooks_state = HooksState(agents=[])
        consumed = consume_knowledge_base_retrieved_references(hooks_state)
        self.assertEqual(consumed, [])


class RetrieveKnowledgeBaseTests(SimpleTestCase):
    @override_settings(
        AWS_BEDROCK_REGION_NAME="us-east-1",
        AWS_BEDROCK_KNOWLEDGE_BASE_ID="kb-id",
    )
    @patch("inline_agents.backends.openai.knowledge_base.get_datasource_id", return_value="ds-id")
    @patch("inline_agents.backends.openai.knowledge_base.boto3.client")
    def test_stores_structured_references_and_returns_joined_text(self, mock_boto_client, _mock_ds):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.retrieve.return_value = {
            "retrievalResults": [
                {
                    "content": {"text": "Answer chunk"},
                    "metadata": {
                        "filename": "faq.docx",
                        "fileUuid": "file-uuid-9",
                        "x-amz-bedrock-kb-source-uri": "s3://internal/faq.docx",
                    },
                }
            ]
        }
        hooks_state = HooksState(agents=[])
        ctx = SimpleNamespace(
            context=SimpleNamespace(
                content_base={"uuid": "cb-uuid"},
                project={"uuid": "proj-uuid"},
                hooks_state=hooks_state,
            )
        )

        result = retrieve_knowledge_base(ctx, "What is the policy?")

        self.assertEqual(result, "Answer chunk")
        self.assertEqual(
            hooks_state.knowledge_base_retrieved_references,
            [{"text": "Answer chunk", "filename": "faq.docx", "fileUuid": "file-uuid-9"}],
        )
        mock_client.retrieve.assert_called_once()
        retrieve_kwargs = mock_client.retrieve.call_args.kwargs
        self.assertEqual(retrieve_kwargs["knowledgeBaseId"], "kb-id")
        self.assertEqual(retrieve_kwargs["retrievalQuery"], {"text": "What is the policy?"})

    @override_settings(
        AWS_BEDROCK_REGION_NAME="us-east-1",
        AWS_BEDROCK_KNOWLEDGE_BASE_ID="kb-id",
    )
    @patch("inline_agents.backends.openai.knowledge_base.get_datasource_id", return_value="ds-id")
    @patch("inline_agents.backends.openai.knowledge_base.boto3.client")
    def test_missing_results_store_empty_references(self, mock_boto_client, _mock_ds):
        mock_client = MagicMock()
        mock_boto_client.return_value = mock_client
        mock_client.retrieve.return_value = {}
        hooks_state = HooksState(agents=[])
        ctx = SimpleNamespace(
            context=SimpleNamespace(
                content_base={"uuid": "cb-uuid"},
                project={"uuid": "proj-uuid"},
                hooks_state=hooks_state,
            )
        )

        result = retrieve_knowledge_base(ctx, "unknown")

        self.assertEqual(result, NO_KNOWLEDGE_BASE_RESPONSE)
        self.assertEqual(hooks_state.knowledge_base_retrieved_references, [])
