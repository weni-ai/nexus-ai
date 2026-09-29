import logging
from typing import Any

import boto3
from agents import RunContextWrapper
from django.conf import settings

from inline_agents.backends.openai.entities import Context
from nexus.utils import get_datasource_id

NO_KNOWLEDGE_BASE_RESPONSE = "No response found in knowledge base."
logger = logging.getLogger(__name__)


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
        source_url = metadata.get("sourceUrl")
        if filename:
            reference["filename"] = filename
        if file_uuid:
            reference["fileUuid"] = file_uuid
        if source_url is not None:
            reference["sourceUrl"] = source_url
        references.append(reference)

    return "\n".join(texts), references


def consume_knowledge_base_retrieved_references(hooks_state: Any) -> list[dict[str, Any]]:
    pending = getattr(hooks_state, "knowledge_base_retrieved_references", None)
    if hooks_state is not None:
        hooks_state.knowledge_base_retrieved_references = None
    if isinstance(pending, list):
        return pending
    return []


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
    project = getattr(ctx.context, "project", None) or {}
    if project.get("is_live_desk_copilot"):
        room_uuid = project.get("room_uuid")
        text, references = _with_specialized_knowledge(
            question=question,
            project_uuid=project.get("uuid"),
            project_text=text,
            project_references=references,
            filters={"room_uuid": room_uuid} if room_uuid else None,
        )
    if hooks_state is not None:
        hooks_state.knowledge_base_retrieved_references = references

    return text


def combine_knowledge_results(
    project_text: str,
    project_references: list[dict[str, Any]],
    specialized_entries: list[dict[str, Any]],
) -> tuple[str, list[dict[str, Any]]]:
    """Label both sources and drop specialized passages that repeat the project KB."""
    project_chunks = []
    if project_text and project_text != NO_KNOWLEDGE_BASE_RESPONSE:
        project_chunks = [chunk.strip() for chunk in project_text.split("\n") if chunk.strip()]

    seen = {chunk.casefold() for chunk in project_chunks}
    lines = [f"[project] {chunk}" for chunk in project_chunks]
    references = [{**reference, "source": reference.get("source") or "project"} for reference in project_references]

    for entry in specialized_entries:
        content = str(entry.get("content") or "").strip()
        if not content or content.casefold() in seen:
            continue
        seen.add(content.casefold())
        source = entry.get("source") or "specialized"
        lines.append(f"[specialized] ({source}) {content}")
        references.append(
            {
                "text": content,
                "source": source,
                "score": entry.get("score"),
                "metadata": entry.get("metadata") or {},
                "knowledge_base": "specialized",
            }
        )

    if not lines:
        return NO_KNOWLEDGE_BASE_RESPONSE, []
    return "\n".join(lines), references


def _with_specialized_knowledge(
    *,
    question: str,
    project_uuid: str | None,
    project_text: str,
    project_references: list[dict[str, Any]],
    filters: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    try:
        from nexus.usecases.projects.specialized_knowledge import retrieve_specialized_knowledge

        entries = retrieve_specialized_knowledge(
            project_uuid=str(project_uuid or ""),
            query=question,
            filters=filters,
        )
    except Exception:
        logger.exception("Specialized knowledge retrieval failed project_uuid=%s", project_uuid)
        return project_text, project_references
    return combine_knowledge_results(project_text, project_references, entries)
