from django.core.management.base import BaseCommand, CommandError

from nexus.projects.models import Project
from nexus.projects.services.project_transfer.exporter import ProjectExporter


class Command(BaseCommand):
    help = "Export a Project and all associated models to a JSON file"

    def add_arguments(self, parser):
        parser.add_argument("--project-uuid", required=True, help="UUID of the project to export")
        parser.add_argument("--output", required=True, help="Path to the output JSON file")
        parser.add_argument(
            "--include-inactive",
            action="store_true",
            help="Include projects marked as inactive (soft-deleted)",
        )

    def handle(self, *args, **options):
        project_uuid = options["project_uuid"]
        output_path = options["output"]
        include_inactive = options["include_inactive"]

        try:
            project = Project.objects.select_related("org", "template_type", "guardrail", "manager_agent").get(
                uuid=project_uuid
            )
        except Project.DoesNotExist as exc:
            raise CommandError(f"Project with uuid '{project_uuid}' does not exist") from exc

        if not project.is_active and not include_inactive:
            raise CommandError(
                f"Project '{project_uuid}' is inactive. Use --include-inactive to export it anyway."
            )

        exporter = ProjectExporter(project)
        payload = exporter.export_json()

        with open(output_path, "w", encoding="utf-8") as output_file:
            output_file.write(payload)

        record_count = sum(len(records) for records in exporter.records.values())
        self.stdout.write(
            self.style.SUCCESS(
                f"Exported project '{project.name}' ({project.uuid}) with {record_count} records to {output_path}"
            )
        )
