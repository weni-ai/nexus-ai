from __future__ import annotations

from typing import Any

from django.db import models

from nexus.intelligences.models import IntegratedIntelligence, Intelligence
from nexus.projects.models import Project, ProjectAuth
from nexus.projects.services.project_transfer.registry import TRANSFER_SPECS


def cleanup_project_tree(project: Project) -> None:
    intelligence_ids = list(
        IntegratedIntelligence.objects.filter(project=project).values_list("intelligence_id", flat=True)
    )
    project.delete()

    for intelligence_id in intelligence_ids:
        if IntegratedIntelligence.objects.filter(intelligence_id=intelligence_id).exists():
            continue
        Intelligence.objects.filter(pk=intelligence_id).delete()


def cleanup_exported_records(bundle: dict[str, Any]) -> None:
    specs = sorted(
        (spec for spec in TRANSFER_SPECS if not spec.is_catalog),
        key=lambda item: item.import_order,
        reverse=True,
    )

    for spec in specs:
        records = bundle.get("records", {}).get(spec.label, [])
        if not records:
            continue

        uuid_field_names = {
            field.name for field in spec.model._meta.fields if isinstance(field, models.UUIDField)
        }
        if "uuid" not in uuid_field_names:
            continue

        for record in records:
            uuid_value = record.get("uuid")
            if uuid_value:
                spec.model.objects.filter(uuid=uuid_value).delete()


def cleanup_before_import(bundle: dict[str, Any], project_uuid: str) -> bool:
    cleaned = False
    project_uuids = {str(project_uuid)}

    source_project_uuid = bundle.get("source_project_uuid")
    if source_project_uuid:
        project_uuids.add(str(source_project_uuid))

    for uuid_value in project_uuids:
        try:
            project = Project.objects.get(uuid=uuid_value)
            ProjectAuth.objects.filter(project=project).delete()
            cleanup_project_tree(project)
            cleaned = True
        except Project.DoesNotExist:
            pass

    cleanup_exported_records(bundle)
    return cleaned
