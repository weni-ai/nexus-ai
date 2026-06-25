from django.conf import settings

CRITERION_TYPE_BASE = "base"
CRITERION_TYPE_CUSTOM = "custom"

VALIDATION_REJECTED_CODES = frozenset(
    {
        "DUPLICATE_CRITERION",
        "AMBIGUOUS_CRITERION",
        "INVALID_CRITERION",
    }
)


def get_base_criteria_config() -> list[dict]:
    return settings.AI_RESOLUTION_BASE_CRITERIA


def get_base_criterion_ids() -> set[str]:
    return {item["id"] for item in get_base_criteria_config()}


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
        "created_at": criterion.created_at.isoformat().replace("+00:00", "Z"),
        "updated_at": updated_at.isoformat().replace("+00:00", "Z"),
    }
