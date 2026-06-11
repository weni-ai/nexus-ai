from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from nexus.projects.models import Project
from nexus.projects.services.project_transfer.constants import SCHEMA_VERSION
from nexus.projects.services.project_transfer.registry import TRANSFER_SPECS, TransferSpec
from nexus.projects.services.project_transfer.serializers import (
    collect_m2m_relations,
    export_bundle_to_json,
    serialize_instance,
)


class ProjectExporter:
    def __init__(self, project: Project):
        self.project = project
        self.user_refs: set[str] = set()
        self.records: dict[str, list[dict[str, Any]]] = {}
        self.m2m: dict[str, list[list[str]]] = {}
        self._seen: dict[str, set[str]] = {}

    def export(self) -> dict[str, Any]:
        for spec in TRANSFER_SPECS:
            self._collect_spec(spec)

        return {
            "schema_version": SCHEMA_VERSION,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "source_project_uuid": str(self.project.uuid),
            "user_refs": sorted(self.user_refs),
            "records": self.records,
            "m2m": self.m2m,
        }

    def export_json(self) -> str:
        return export_bundle_to_json(self.export())

    def _collect_spec(self, spec: TransferSpec) -> None:
        queryset = spec.collect(self.project)
        instances = list(queryset)
        if not instances:
            return

        label_records = self.records.setdefault(spec.label, [])
        seen_ids = self._seen.setdefault(spec.label, set())
        serialized_instances: list = []

        for instance in instances:
            export_id = spec.export_id(instance)
            if export_id in seen_ids:
                continue
            seen_ids.add(export_id)
            label_records.append(serialize_instance(instance, spec, self.user_refs))
            serialized_instances.append(instance)

        if spec.m2m_fields:
            m2m_data = collect_m2m_relations(serialized_instances, spec)
            for label, relations in m2m_data.items():
                existing = self.m2m.setdefault(label, [])
                existing_keys = {tuple(pair) for pair in existing}
                for relation in relations:
                    key = tuple(relation)
                    if key not in existing_keys:
                        existing.append(relation)
                        existing_keys.add(key)
