from datetime import timezone as dt_timezone

from django.conf import settings
from django.utils import timezone

CRITERION_TYPE_BASE = "base"
CRITERION_TYPE_CUSTOM = "custom"


def get_base_criteria_config() -> list[dict]:
    return settings.AI_RESOLUTION_BASE_CRITERIA


def get_base_criterion_ids() -> set[str]:
    return {item["id"] for item in get_base_criteria_config()}


def format_iso8601_z(value) -> str:
    if timezone.is_naive(value):
        value = timezone.make_aware(value, dt_timezone.utc)
    return value.astimezone(dt_timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def serialize_base_criterion(item: dict) -> dict:
    return {
        "id": item["id"],
        "text": item["text"],
        "type": CRITERION_TYPE_BASE,
        "editable": False,
        "deletable": False,
    }


def serialize_custom_criterion(criterion) -> dict:
    updated_at = criterion.modified_at or criterion.created_at
    return {
        "id": str(criterion.uuid),
        "text": criterion.text,
        "type": CRITERION_TYPE_CUSTOM,
        "editable": True,
        "deletable": True,
        "created_at": format_iso8601_z(criterion.created_at),
        "updated_at": format_iso8601_z(updated_at),
    }
