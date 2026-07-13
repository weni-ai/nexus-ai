from typing import Optional

from nexus.utils import get_datasource_id

KB_VERSION_DRAFT = "DRAFT"
KB_VERSION_METADATA_KEY = "version"
DEFAULT_KNOWLEDGE_BASE_VERSION = "1"


def build_knowledge_base_filter(
    content_base_uuid: str,
    project_uuid: Optional[str],
    knowledge_base_version: str,
    include_draft: bool = False,
    data_source_id: Optional[str] = None,
) -> dict:
    version_filter = (
        {
            "orAll": [
                {"equals": {"key": KB_VERSION_METADATA_KEY, "value": knowledge_base_version}},
                {"equals": {"key": KB_VERSION_METADATA_KEY, "value": KB_VERSION_DRAFT}},
            ]
        }
        if include_draft
        else {"equals": {"key": KB_VERSION_METADATA_KEY, "value": knowledge_base_version}}
    )
    return {
        "andAll": [
            {"equals": {"key": "contentBaseUuid", "value": str(content_base_uuid)}},
            {
                "equals": {
                    "key": "x-amz-bedrock-kb-data-source-id",
                    "value": data_source_id or get_datasource_id(project_uuid),
                }
            },
            version_filter,
        ]
    }
