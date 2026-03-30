"""Project channels (WWC) and default preview channel resolution."""

from __future__ import annotations

from uuid import UUID

from django.db import transaction

from nexus.projects.models import Channel, Project


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

    Channel.objects.filter(project=project).update(is_default_for_preview=False)

    return Channel.objects.create(
        uuid=cid,
        project=project,
        channel_type=str(channel_type),
        is_default_for_preview=True,
    )
