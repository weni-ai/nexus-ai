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
        input_path = options["input"]
        user_email = options["user_email"]
        target_org_uuid = options["org_uuid"]
        target_project_uuid = options["project_uuid"]
        overwrite = not options["no_overwrite"]
        dry_run = options["dry_run"]
        skip_if_exists = options["skip_if_exists"]

        with open(input_path, encoding="utf-8") as input_file:
            raw = input_file.read()

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
            raise CommandError(str(exc)) from exc

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
