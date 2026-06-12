from __future__ import annotations

import logging
from typing import Any
from uuid import UUID

from django.db import models, transaction

from nexus.orgs.models import Org, OrgAuth
from nexus.projects.models import Project, ProjectAuth, ProjectAuthorizationRole
from nexus.projects.services.project_transfer.constants import IMPORT_UNIQUE_LOOKUPS
from nexus.projects.services.project_transfer.project_cleanup import cleanup_before_import
from nexus.projects.services.project_transfer.registry import (
    TRANSFER_SPECS,
    TransferSpec,
    get_spec_by_label,
)
from nexus.projects.services.project_transfer.serializers import load_export_bundle, resolve_user
from nexus.users.models import User

logger = logging.getLogger(__name__)


class ProjectImporter:
    def __init__(
        self,
        bundle: dict[str, Any],
        user_email: str,
        *,
        target_org_uuid: str | None = None,
        target_project_uuid: str | None = None,
        overwrite: bool = True,
        dry_run: bool = False,
        skip_if_exists: bool = False,
    ):
        self.bundle = bundle
        self.user = resolve_user(user_email)
        self.target_org_uuid = str(target_org_uuid) if target_org_uuid else None
        self.target_project_uuid = str(target_project_uuid) if target_project_uuid else None
        self.overwrite = overwrite
        self.dry_run = dry_run
        self.skip_if_exists = skip_if_exists
        self.id_map: dict[tuple[str, str], models.Model] = {}
        self.warnings: list[str] = []

    @classmethod
    def from_json(
        cls,
        raw: str,
        user_email: str,
        *,
        target_org_uuid: str | None = None,
        target_project_uuid: str | None = None,
        overwrite: bool = True,
        dry_run: bool = False,
        skip_if_exists: bool = False,
    ) -> "ProjectImporter":
        return cls(
            load_export_bundle(raw),
            user_email,
            target_org_uuid=target_org_uuid,
            target_project_uuid=target_project_uuid,
            overwrite=overwrite,
            dry_run=dry_run,
            skip_if_exists=skip_if_exists,
        )

    def import_project(self) -> Project:
        with transaction.atomic():
            project = self._run_import()
            if self.dry_run:
                transaction.set_rollback(True)
            return project

    def _run_import(self) -> Project:
        self._validate_target_overrides()
        if self.overwrite:
            self._cleanup_existing_data()
        else:
            self._check_existing_records()
        self._prepare_org_overrides()
        sorted_specs = sorted(TRANSFER_SPECS, key=lambda spec: spec.import_order)

        for spec in sorted_specs:
            records = self.bundle.get("records", {}).get(spec.label, [])
            if not records:
                continue
            for record in records:
                self._import_record(spec, record)

        self._import_m2m()
        self._log_warnings()
        project = self._get_imported_project()
        self._ensure_import_user_project_auth(project)
        return project

    def _validate_target_overrides(self) -> None:
        if self.target_org_uuid:
            try:
                Org.objects.get(uuid=self.target_org_uuid)
            except Org.DoesNotExist as exc:
                raise ValueError(f"Target org with uuid '{self.target_org_uuid}' does not exist") from exc

        if (
            not self.overwrite
            and self.target_project_uuid
            and Project.objects.filter(uuid=self.target_project_uuid).exists()
        ):
            raise ValueError(f"Target project with uuid '{self.target_project_uuid}' already exists")

    def _effective_project_uuid(self) -> str | None:
        return self.target_project_uuid or self.bundle.get("source_project_uuid")

    def _cleanup_existing_data(self) -> None:
        project_uuid = self._effective_project_uuid()
        if not project_uuid:
            return

        cleaned_project = cleanup_before_import(self.bundle, project_uuid)
        if cleaned_project:
            self.warnings.append(
                f"Existing data for project '{project_uuid}' was removed before import."
            )
        else:
            self.warnings.append(
                "Existing exported records with matching UUIDs were removed before import."
            )

    def _prepare_org_overrides(self) -> None:
        if self.target_org_uuid:
            target_org = Org.objects.get(uuid=self.target_org_uuid)
            for record in self.bundle.get("records", {}).get("orgs.Org", []):
                self.id_map[("orgs.Org", record["_export_id"])] = target_org

            self.warnings.append(
                f"Using existing org '{target_org.name}' ({target_org.uuid}). "
                "Org and OrgAuth records from the export were skipped."
            )
            return

        if not self.overwrite:
            return

        for record in self.bundle.get("records", {}).get("orgs.Org", []):
            org_uuid = record.get("uuid")
            if not org_uuid:
                continue
            try:
                org = Org.objects.get(uuid=org_uuid)
            except Org.DoesNotExist:
                continue
            self.id_map[("orgs.Org", record["_export_id"])] = org
            self.warnings.append(
                f"Reusing existing org '{org.name}' ({org.uuid}) during overwrite import."
            )

    def _should_skip_record(self, spec: TransferSpec, record: dict[str, Any]) -> bool:
        if self.target_org_uuid and spec.label in {"orgs.Org", "orgs.OrgAuth"}:
            return True

        if spec.label == "orgs.Org" and ("orgs.Org", record["_export_id"]) in self.id_map:
            return True

        if spec.label == "projects.ProjectAuth":
            return True

        if spec.label == "orgs.OrgAuth":
            org = self.id_map.get(("orgs.Org", record.get("org_ref")))
            if org and OrgAuth.objects.filter(org=org, user=self.user).exists():
                return True

        return False

    def _check_existing_records(self) -> None:
        if not self.skip_if_exists:
            return
            org_records = self.bundle.get("records", {}).get("orgs.Org", [])
            for record in org_records:
                org_uuid = record.get("uuid") or record.get("_export_id")
                if org_uuid and Org.objects.filter(uuid=org_uuid).exists():
                    raise ValueError(f"Org with uuid '{org_uuid}' already exists")

        project_uuid = self.target_project_uuid or self.bundle.get("source_project_uuid")
        if project_uuid and Project.objects.filter(uuid=project_uuid).exists():
            raise ValueError(f"Project with uuid '{project_uuid}' already exists")

    def _import_record(self, spec: TransferSpec, record: dict[str, Any]) -> None:
        if self._should_skip_record(spec, record):
            return

        export_id = record["_export_id"]
        map_key = (spec.label, export_id)

        if map_key in self.id_map:
            return

        if spec.is_catalog:
            instance = self._get_or_create_catalog(spec, record)
            self.id_map[map_key] = instance
            return

        existing = self._find_existing_instance(spec, record)
        if existing is not None:
            self.id_map[map_key] = existing
            return

        field_values = self._build_field_values(spec, record)
        if spec.label == "projects.Project" and self.target_project_uuid:
            field_values["uuid"] = UUID(self.target_project_uuid)
        if spec.label == "inline_agents.Agent":
            field_values["project"] = self._resolve_agent_project(record)

        unique_lookup = IMPORT_UNIQUE_LOOKUPS.get(spec.label)
        if unique_lookup:
            lookup = {field_name: field_values[field_name] for field_name in unique_lookup}
            defaults = {
                key: value
                for key, value in field_values.items()
                if key not in lookup
            }
            instance, _created = spec.model.objects.update_or_create(**lookup, defaults=defaults)
        else:
            instance = spec.model.objects.create(**field_values)
        self.id_map[map_key] = instance

    def _find_existing_instance(self, spec: TransferSpec, record: dict[str, Any]) -> models.Model | None:
        if self.overwrite:
            return None

        if record.get("uuid"):
            uuid_field_names = {field.name for field in spec.model._meta.fields if isinstance(field, models.UUIDField)}
            if "uuid" in uuid_field_names:
                try:
                    return spec.model.objects.get(uuid=record["uuid"])
                except spec.model.DoesNotExist:
                    return None
        return None

    def _get_or_create_catalog(self, spec: TransferSpec, record: dict[str, Any]) -> models.Model:
        export_id = record["_export_id"]
        map_key = (spec.label, export_id)
        if map_key in self.id_map:
            return self.id_map[map_key]

        lookup = self._catalog_lookup(spec, record)
        defaults = self._build_field_values(spec, record, skip_fks=False)

        for key in list(defaults.keys()):
            if key in lookup:
                defaults.pop(key, None)

        instance, _created = spec.model.objects.update_or_create(**lookup, defaults=defaults)
        return instance

    def _catalog_lookup(self, spec: TransferSpec, record: dict[str, Any]) -> dict[str, Any]:
        if spec.label == "inline_agents.Guardrail":
            return {"identifier": record["identifier"], "version": record["version"]}
        if spec.label in {
            "inline_agents.AgentType",
            "inline_agents.AgentCategory",
            "inline_agents.AgentGroup",
            "inline_agents.AgentSystem",
            "inline_agents.MCP",
        }:
            return {"slug": record["slug"]}
        if spec.label == "inline_agents.MCPConfigOption":
            mcp = self._resolve_ref("inline_agents.MCP", record["mcp_ref"])
            return {"mcp": mcp, "name": record["name"]}
        if spec.label == "inline_agents.MCPCredentialTemplate":
            mcp = self._resolve_ref("inline_agents.MCP", record["mcp_ref"])
            return {"mcp": mcp, "name": record["name"]}
        if spec.label == "inline_agents.AgentGroupModal":
            group = self._resolve_ref("inline_agents.AgentGroup", record["group_ref"])
            return {"group": group}
        if spec.label in {"inline_agents.ManagerAgent", "inline_agents.ModelProvider", "actions.TemplateAction"}:
            if spec.label == "inline_agents.ModelProvider":
                return {"model_vendor": record["model_vendor"]}
            return {"uuid": UUID(str(record["uuid"]))}
        if spec.label == "projects.TemplateType":
            if record.get("uuid"):
                return {"uuid": UUID(str(record["uuid"]))}
            return {"name": record["name"]}

        if record.get("uuid"):
            return {"uuid": UUID(str(record["uuid"]))}
        raise ValueError(f"Unable to resolve catalog lookup for {spec.label}")

    def _build_field_values(
        self,
        spec: TransferSpec,
        record: dict[str, Any],
        *,
        skip_fks: bool = False,
    ) -> dict[str, Any]:
        values: dict[str, Any] = {}

        for field in spec.model._meta.fields:
            if field.auto_created:
                continue

            field_name = field.name

            if isinstance(field, models.AutoField):
                continue

            if isinstance(field, models.ForeignKey):
                if skip_fks:
                    continue

                ref_key = f"{field_name}_ref"
                ref_value = record.get(ref_key)
                if ref_value is None:
                    values[field_name] = None
                    continue

                if field_name in {"created_by", "modified_by", "user"} or (
                    field.related_model and field.related_model._meta.label_lower == "users.user"
                ):
                    values[field_name] = self.user
                    continue

                if spec.label == "inline_agents.Agent" and field_name == "project":
                    continue

                related_spec = get_spec_by_label(field.related_model._meta.label)
                if related_spec is None:
                    continue

                values[field_name] = self._resolve_ref(related_spec.label, ref_value)
                continue

            if field_name not in record:
                continue

            if field_name in spec.import_overrides:
                values[field_name] = spec.import_overrides[field_name]
                continue

            value = record[field_name]
            if isinstance(field, models.UUIDField) and value is not None and field_name != "uuid":
                values[field_name] = UUID(str(value))
            elif field_name == "uuid" and value is not None:
                values[field_name] = UUID(str(value))
            else:
                values[field_name] = value

        for field_name, override_value in spec.import_overrides.items():
            if field_name.endswith("_ref"):
                continue
            values[field_name] = override_value

        return values

    def _resolve_agent_project(self, record: dict[str, Any]) -> Project:
        project_ref = record.get("project_ref")
        if project_ref:
            mapped_project = self.id_map.get(("projects.Project", project_ref))
            if mapped_project is not None:
                return mapped_project

        return self._resolve_import_target_project()

    def _resolve_import_target_project(self) -> Project:
        if self.target_project_uuid:
            return Project.objects.get(uuid=self.target_project_uuid)

        source_project_uuid = self.bundle.get("source_project_uuid")
        for project_record in self.bundle.get("records", {}).get("projects.Project", []):
            export_id = project_record["_export_id"]
            if export_id == source_project_uuid or project_record.get("uuid") == source_project_uuid:
                mapped_project = self.id_map.get(("projects.Project", export_id))
                if mapped_project is not None:
                    return mapped_project

        raise ValueError("Imported project not found for agent project assignment")

    def _resolve_ref(self, label: str, export_id: str) -> models.Model:
        instance = self.id_map.get((label, export_id))
        if instance is not None:
            return instance

        spec = get_spec_by_label(label)
        if spec is None:
            raise ValueError(f"Unknown model label '{label}'")

        raise ValueError(f"Unresolved reference '{label}' -> '{export_id}'")

    def _import_m2m(self) -> None:
        for relation_label, pairs in self.bundle.get("m2m", {}).items():
            model_label, field_name = relation_label.rsplit(".", 1)
            spec = get_spec_by_label(model_label)
            if spec is None:
                continue

            for source_id, target_id in pairs:
                source = self.id_map.get((spec.label, source_id))
                if source is None:
                    continue

                target_spec = self._resolve_m2m_target_spec(spec, field_name, target_id)
                if target_spec is None:
                    continue

                target = self.id_map.get((target_spec.label, target_id))
                if target is None:
                    continue

                getattr(source, field_name).add(target)

    def _resolve_m2m_target_spec(
        self,
        source_spec: TransferSpec,
        field_name: str,
        target_id: str,
    ) -> TransferSpec | None:
        field = source_spec.model._meta.get_field(field_name)
        return get_spec_by_label(field.related_model._meta.label)

    def _get_imported_project(self) -> Project:
        if self.target_project_uuid:
            return Project.objects.get(uuid=self.target_project_uuid)

        project_uuid = self.bundle.get("source_project_uuid")
        if project_uuid:
            return Project.objects.get(uuid=project_uuid)

        for (label, _), instance in self.id_map.items():
            if label == "projects.Project":
                return instance

        raise ValueError("Imported project not found in id map")

    def _ensure_import_user_project_auth(self, project: Project) -> None:
        ProjectAuth.objects.update_or_create(
            user=self.user,
            project=project,
            defaults={
                "role": ProjectAuthorizationRole.MODERATOR.value,
                "is_active": True,
            },
        )

    def _log_warnings(self) -> None:
        if self.bundle.get("records", {}).get("projects.ProjectAuth"):
            self.warnings.append(
                "ProjectAuth records from the export were skipped. "
                f"Moderator access was granted to '{self.user.email}'."
            )
        if self.bundle.get("records", {}).get("projects.ProjectApiToken"):
            self.warnings.append(
                "ProjectApiToken records were imported with enabled=False because raw tokens cannot be recovered."
            )
        if self.bundle.get("records", {}).get("inline_agents.AgentCredential") or self.bundle.get(
            "records", {}
        ).get("inline_agents.ProjectModelProvider"):
            self.warnings.append(
                "Encrypted credentials require the same ENCRYPTION_KEY in the target environment."
            )

        for warning in self.warnings:
            logger.warning(warning)
