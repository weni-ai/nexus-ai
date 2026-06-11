from __future__ import annotations

import json
from datetime import date, datetime
from decimal import Decimal
from typing import Any
from uuid import UUID

from django.db import models
from django.db.models.fields.files import FieldFile

from nexus.projects.services.project_transfer.constants import USER_FK_FIELD_NAMES
from nexus.projects.services.project_transfer.registry import TRANSFER_SPECS, TransferSpec, get_spec_for_model
from nexus.users.models import User


def _json_safe(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, FieldFile):
        return value.name or None
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    return str(value)


def export_id_for_instance(instance: models.Model, spec: TransferSpec) -> str:
    return spec.export_id(instance)


def serialize_instance(
    instance: models.Model,
    spec: TransferSpec,
    user_refs: set[str],
) -> dict[str, Any]:
    data: dict[str, Any] = {"_export_id": export_id_for_instance(instance, spec)}

    for field in spec.model._meta.fields:
        if field.auto_created:
            continue

        if isinstance(field, models.AutoField):
            continue

        field_name = field.name
        value = getattr(instance, field_name)

        if isinstance(field, models.ForeignKey):
            if value is None:
                data[f"{field_name}_ref"] = None
                continue

            if field_name in USER_FK_FIELD_NAMES or (
                field.related_model and field.related_model._meta.label_lower == "users.user"
            ):
                user_refs.add(value.email)
                data[f"{field_name}_ref"] = value.email
                continue

            related_spec = get_spec_for_model(field.related_model)
            if related_spec is None:
                data[f"{field_name}_ref"] = str(value.pk)
                continue

            data[f"{field_name}_ref"] = export_id_for_instance(value, related_spec)
            continue

        if field_name in USER_FK_FIELD_NAMES:
            continue

        data[field_name] = _json_safe(value)

    return data


def collect_m2m_relations(
    instances: list[models.Model],
    spec: TransferSpec,
) -> dict[str, list[list[str]]]:
    m2m_data: dict[str, list[list[str]]] = {}

    for m2m_field_name in spec.m2m_fields:
        field = spec.model._meta.get_field(m2m_field_name)
        related_spec = get_spec_for_model(field.related_model)
        if related_spec is None:
            continue

        label = f"{spec.label}.{m2m_field_name}"
        relations: list[list[str]] = []

        for instance in instances:
            source_id = export_id_for_instance(instance, spec)
            for related in getattr(instance, m2m_field_name).all():
                relations.append([source_id, export_id_for_instance(related, related_spec)])

        if relations:
            m2m_data[label] = relations

    return m2m_data


def export_bundle_to_json(bundle: dict[str, Any]) -> str:
    return json.dumps(bundle, indent=2, ensure_ascii=False, default=str)


def load_export_bundle(raw: str) -> dict[str, Any]:
    bundle = json.loads(raw)
    if bundle.get("schema_version") != "1.0":
        raise ValueError(f"Unsupported schema version: {bundle.get('schema_version')}")
    return bundle


def resolve_user(user_email: str) -> User:
    try:
        return User.objects.get(email=user_email)
    except User.DoesNotExist as exc:
        raise ValueError(f"User with email '{user_email}' does not exist in target environment") from exc
