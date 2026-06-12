from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from nexus.projects.services.project_transfer.importer import ProjectImporter


class Command(BaseCommand):
    help = "Import a Project export JSON into the current environment"

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True, help="Path to the export JSON file")
        parser.add_argument(
            "--user-email",
            required=True,
            help="Email of an existing user in the target environment for ownership references",
        )
        parser.add_argument(
            "--org-uuid",
            default=None,
            help="UUID of an existing org in the target environment (skips Org and OrgAuth import)",
        )
        parser.add_argument(
            "--project-uuid",
            default=None,
            help="UUID to assign to the imported project instead of the one from the export",
        )
        parser.add_argument(
            "--no-overwrite",
            action="store_true",
            help="Do not remove existing project data before import (fails if target data already exists)",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Run the import inside a transaction and roll it back at the end",
        )
        parser.add_argument(
            "--skip-if-exists",
            action="store_true",
            help="Abort if Org or Project UUID from the export already exists",
        )

    def handle(self, *args, **options):
        input_path = Path(options["input"])
        user_email = options["user_email"]
        target_org_uuid = options["org_uuid"]
        target_project_uuid = options["project_uuid"]
        overwrite = not options["no_overwrite"]
        dry_run = options["dry_run"]
        skip_if_exists = options["skip_if_exists"]

        if not input_path.is_file():
            raise CommandError(f"Input file not found: {input_path}")

        raw = input_path.read_text(encoding="utf-8")
        if not raw.strip():
            raise CommandError(
                f"Input file is empty: {input_path}. "
                "Copy the export JSON into the pod or mount it as a volume before running import."
            )

        try:
            importer = ProjectImporter.from_json(
                raw,
                user_email,
                target_org_uuid=target_org_uuid,
                target_project_uuid=target_project_uuid,
                overwrite=overwrite,
                dry_run=dry_run,
                skip_if_exists=skip_if_exists,
            )
            project = importer.import_project()
        except ValueError as exc:
            message = str(exc)
            if message.startswith("Expecting value"):
                raise CommandError(
                    f"Invalid or empty JSON in {input_path}: {message}. "
                    "Verify the file was exported with export_project and transferred completely."
                ) from exc
            raise CommandError(message) from exc

        for warning in importer.warnings:
            self.stdout.write(self.style.WARNING(warning))

        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run completed. No changes were persisted."))
            return

        self.stdout.write(
            self.style.SUCCESS(
                f"Imported project '{project.name}' ({project.uuid}) from {input_path}"
            )
        )
