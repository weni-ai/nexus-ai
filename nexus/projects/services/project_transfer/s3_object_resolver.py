from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import unquote, urlparse


@dataclass(frozen=True)
class S3ObjectRef:
    bucket: str
    key: str
    source_model: str
    source_uuid: str
    is_metadata: bool = False


def bedrock_object_key(content_base_uuid: str, file_name: str) -> str:
    return f"{content_base_uuid}/{file_name}"


def bedrock_metadata_key(content_base_uuid: str, file_name: str) -> str:
    return f"{content_base_uuid}/{file_name}.metadata.json"


def parse_s3_object_url(url: str) -> tuple[str, str] | None:
    if not url:
        return None

    parsed = urlparse(url)
    host = parsed.netloc
    path = unquote(parsed.path.lstrip("/"))

    if not path:
        return None

    if ".s3." in host and host.endswith(".amazonaws.com"):
        bucket = host.split(".s3.", maxsplit=1)[0]
        return bucket, path

    if host.startswith("s3.") and host.endswith(".amazonaws.com"):
        parts = path.split("/", 1)
        if len(parts) == 2:
            return parts[0], parts[1]

    return None


def resolve_bedrock_key(
    *,
    file_url: str | None,
    content_base_uuid: str,
    file_name: str | None,
) -> str | None:
    if file_url:
        parsed = parse_s3_object_url(file_url)
        if parsed:
            return parsed[1]

    if file_name:
        return bedrock_object_key(content_base_uuid, file_name)

    return None
