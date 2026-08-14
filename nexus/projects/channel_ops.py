"""Project channels (WWC) and default preview channel resolution."""

from __future__ import annotations

from uuid import UUID

from django.db import transaction

from nexus.projects.models import Channel, Project

MAILROOM_FLOW_SIMULATOR_CHANNEL_UUID = "440099cf-200c-4d45-a8e7-4a564f4a0e8b"
MAILROOM_FLOW_SIMULATOR_CONTACT_URN = "tel:+12065551212"


def is_mailroom_flow_simulator_traffic(
    contact_urn: str | None,
    channel_uuid: str | UUID | None,
) -> bool:
    normalized_contact_urn = (contact_urn or "").strip()
    normalized_channel_uuid = str(channel_uuid).strip() if channel_uuid is not None else ""
    return (
        normalized_contact_urn == MAILROOM_FLOW_SIMULATOR_CONTACT_URN
        or normalized_channel_uuid == MAILROOM_FLOW_SIMULATOR_CHANNEL_UUID
    )


def get_default_channel_uuid(project_uuid: str) -> str | None:
    row = Channel.objects.filter(project_id=project_uuid, is_default_for_preview=True).only("uuid").first()
    return str(row.uuid) if row else None


def channel_matches_default_preview(project_uuid: str, channel_uuid: str | None) -> bool:
    default = get_default_channel_uuid(project_uuid)
    if not default or channel_uuid is None:
        return False
    sent = str(channel_uuid).strip()
    if not sent:
        return False
    return sent == str(default)


@transaction.atomic
def create_channel_from_wwc_event(project_uuid: str, channel_uuid: str, channel_type: str) -> Channel:
    try:
        project = Project.objects.get(uuid=UUID(str(project_uuid)))
    except ValueError as exc:
        raise ValueError("invalid project_uuid") from exc
    try:
        cid = UUID(str(channel_uuid))
    except ValueError as exc:
        raise ValueError("invalid channel_uuid") from exc

    return Channel.objects.create(
        uuid=cid,
        project=project,
        channel_type=str(channel_type),
        is_default_for_preview=True,
    )
