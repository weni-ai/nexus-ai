from typing import Any

import boto3
from agents import RunContextWrapper
from django.conf import settings

from inline_agents.backends.openai.entities import Context
from nexus.utils import get_datasource_id

NO_KNOWLEDGE_BASE_RESPONSE = "No response found in knowledge base."


def format_knowledge_base_retrieval_results(
    retrieval_results: list | None,
) -> tuple[str, list[dict[str, Any]]]:
    if not retrieval_results:
        return NO_KNOWLEDGE_BASE_RESPONSE, []

    texts: list[str] = []
    references: list[dict[str, Any]] = []
    for result in retrieval_results:
        if not isinstance(result, dict):
            continue
        content = result.get("content")
        content = content if isinstance(content, dict) else {}
        text = content.get("text") or ""
        texts.append(text)

        metadata = result.get("metadata")
        metadata = metadata if isinstance(metadata, dict) else {}
        reference: dict[str, Any] = {"text": text}
        filename = metadata.get("filename")
        file_uuid = metadata.get("fileUuid")
        if filename:
            reference["filename"] = filename
        if file_uuid:
            reference["fileUuid"] = file_uuid
        references.append(reference)

    return "\n".join(texts), references


def consume_knowledge_base_retrieved_references(hooks_state: Any, result: Any) -> Any:
    pending = getattr(hooks_state, "knowledge_base_retrieved_references", None)
    if pending is None:
        return result
    hooks_state.knowledge_base_retrieved_references = None
    return pending


def retrieve_knowledge_base(ctx: RunContextWrapper[Context], question: str) -> str:
    client = boto3.client("bedrock-agent-runtime", region_name=settings.AWS_BEDROCK_REGION_NAME)
    content_base_uuid: str | None = ctx.context.content_base.get("uuid")

    retrieve_params = {
        "knowledgeBaseId": settings.AWS_BEDROCK_KNOWLEDGE_BASE_ID,
        "retrievalQuery": {"text": question},
    }

    combined_filter = {
        "andAll": [
            {"equals": {"key": "contentBaseUuid", "value": content_base_uuid}},
            {
                "equals": {
                    "key": "x-amz-bedrock-kb-data-source-id",
                    "value": get_datasource_id(ctx.context.project.get("uuid")),
                }
            },
        ]
    }

    if content_base_uuid:
        retrieve_params["retrievalConfiguration"] = {
            "vectorSearchConfiguration": {
                "filter": combined_filter,
            }
        }

    response = client.retrieve(**retrieve_params)
    retrieval_results = response.get("retrievalResults")
    text, references = format_knowledge_base_retrieval_results(retrieval_results)

    hooks_state = getattr(ctx.context, "hooks_state", None)
    if hooks_state is not None:
        hooks_state.knowledge_base_retrieved_references = references if retrieval_results else None

    return text
