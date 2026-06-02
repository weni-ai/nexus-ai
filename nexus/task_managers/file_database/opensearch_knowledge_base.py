import base64
import json
import logging
from functools import lru_cache
from typing import Any

import boto3
from django.conf import settings
from opensearchpy import AWSV4SignerAuth, OpenSearch, RequestsHttpConnection

logger = logging.getLogger(__name__)


class OpenSearchKnowledgeBaseError(Exception):
    pass


@lru_cache(maxsize=1)
def get_opensearch_kb_config() -> dict[str, str]:
    try:
        bedrock_agent_client = boto3.client("bedrock-agent", region_name=settings.AWS_BEDROCK_REGION_NAME)
        response = bedrock_agent_client.get_knowledge_base(knowledgeBaseId=settings.AWS_BEDROCK_KNOWLEDGE_BASE_ID)
        kb_info = response["knowledgeBase"]
        storage_conf = kb_info.get("storageConfiguration", {})

        if storage_conf.get("type") != "OPENSEARCH_SERVERLESS":
            raise OpenSearchKnowledgeBaseError("Knowledge Base does not use OpenSearch Serverless")

        os_conf = storage_conf["opensearchServerlessConfiguration"]
        collection_arn = os_conf["collectionArn"]
        partes_arn = collection_arn.split(":")
        regiao = partes_arn[3]
        collection_id = partes_arn[5].replace("collection/", "")
        host = f"{collection_id}.{regiao}.aoss.amazonaws.com"

        field_mapping = os_conf.get("fieldMapping", {})
        metadata_field = field_mapping.get("metadataField")
        text_field = field_mapping.get("textField")

        if not metadata_field or not text_field:
            raise OpenSearchKnowledgeBaseError("Knowledge Base field mapping is incomplete")

        return {
            "host": host,
            "metadata_field": metadata_field,
            "text_field": text_field,
            "region": regiao,
            "index_name": settings.AWS_BEDROCK_OPENSEARCH_INDEX_NAME,
        }
    except OpenSearchKnowledgeBaseError:
        raise
    except Exception as e:
        logger.exception("Failed to fetch OpenSearch KB config")
        raise OpenSearchKnowledgeBaseError(f"Failed to fetch Knowledge Base config: {e}") from e


@lru_cache(maxsize=1)
def get_opensearch_client() -> OpenSearch:
    config = get_opensearch_kb_config()
    credentials = boto3.Session().get_credentials()
    auth = AWSV4SignerAuth(credentials, config["region"], "aoss")
    return OpenSearch(
        hosts=[{"host": config["host"], "port": 443}],
        http_auth=auth,
        use_ssl=True,
        verify_certs=True,
        connection_class=RequestsHttpConnection,
        pool_maxsize=20,
    )


def _encode_cursor(search_after: list[Any]) -> str:
    payload = json.dumps(search_after)
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("utf-8")


def _decode_cursor(cursor: str) -> list[Any]:
    try:
        payload = base64.urlsafe_b64decode(cursor.encode("utf-8")).decode("utf-8")
        search_after = json.loads(payload)
        if not isinstance(search_after, list):
            raise ValueError("cursor must decode to a list")
        return search_after
    except (json.JSONDecodeError, ValueError, UnicodeDecodeError) as e:
        raise ValueError("Invalid cursor") from e


def _extract_filename(source: dict[str, Any]) -> str | None:
    filename = source.get("filename")
    if filename:
        return filename

    source_uri = source.get("x-amz-bedrock-kb-source-uri")
    if source_uri:
        return source_uri.rstrip("/").split("/")[-1]

    return None


def _format_chunk(hit: dict[str, Any], text_field: str, metadata_field: str) -> dict[str, Any]:
    source = hit.get("_source", {})
    return {
        "id": hit.get("_id"),
        "text": source.get(text_field, ""),
        "filename": _extract_filename(source),
        "file_uuid": source.get("fileUuid"),
        "metadata": {
            "contentBaseUuid": source.get("contentBaseUuid"),
            "fileUuid": source.get("fileUuid"),
            "x-amz-bedrock-kb-data-source-id": source.get("x-amz-bedrock-kb-data-source-id"),
            "x-amz-bedrock-kb-source-uri": source.get("x-amz-bedrock-kb-source-uri"),
            metadata_field: source.get(metadata_field),
        },
    }


def _build_chunk_filters(content_base_uuid: str, data_source_id: str) -> list[dict[str, Any]]:
    # Custom metadata attributes and Bedrock-managed fields are top-level in the index.
    return [
        {"term": {"contentBaseUuid.keyword": content_base_uuid}},
        {"term": {"x-amz-bedrock-kb-data-source-id.keyword": data_source_id}},
    ]


def list_chunks(
    content_base_uuid: str,
    data_source_id: str,
    page_size: int,
    cursor: str | None = None,
) -> dict[str, Any]:
    config = get_opensearch_kb_config()
    client = get_opensearch_client()
    metadata_field = config["metadata_field"]
    filters = _build_chunk_filters(content_base_uuid, data_source_id)

    body: dict[str, Any] = {
        "size": page_size,
        "track_total_hits": True,
        "sort": [{"_id": "asc"}],
        "query": {"bool": {"filter": filters}},
    }

    if cursor:
        body["search_after"] = _decode_cursor(cursor)

    try:
        response = client.search(body=body, index=config["index_name"])
    except ValueError:
        raise
    except Exception as e:
        logger.exception("OpenSearch search failed")
        raise OpenSearchKnowledgeBaseError(f"OpenSearch search failed: {e}") from e

    hits = response["hits"]["hits"]
    total = response["hits"]["total"]["value"]
    results = [_format_chunk(hit, config["text_field"], metadata_field) for hit in hits]

    next_cursor = None
    if hits and len(hits) == page_size:
        next_cursor = _encode_cursor(hits[-1]["sort"])

    return {
        "count": total,
        "page_size": page_size,
        "next_cursor": next_cursor,
        "results": results,
    }
