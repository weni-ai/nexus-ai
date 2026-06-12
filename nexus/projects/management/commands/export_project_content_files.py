from django.core.management.base import BaseCommand, CommandError

from nexus.projects.models import Project
from nexus.projects.services.project_transfer.content_files_collector import UnsupportedIndexerError
from nexus.projects.services.project_transfer.content_files_constants import DEFAULT_PRESIGNED_URL_EXPIRATION_SECONDS
from nexus.projects.services.project_transfer.content_files_manifest import ContentFilesManifestExporter


class Command(BaseCommand):
    help = (
        "Export presigned download URLs for Bedrock content base files "
        "(ContentBaseFile, ContentBaseText, ContentBaseLink) to a manifest JSON"
    )

    def add_arguments(self, parser):
        parser.add_argument("--project-uuid", required=True, help="UUID of the Bedrock project")
        parser.add_argument("--output", required=True, help="Path to the output manifest JSON file")
        parser.add_argument(
            "--expires-in",
            type=int,
            default=DEFAULT_PRESIGNED_URL_EXPIRATION_SECONDS,
            help="Presigned URL expiration in seconds (default: 86400)",
        )
        parser.add_argument(
            "--no-metadata",
            action="store_true",
            help="Do not include Bedrock .metadata.json sidecar files",
        )

    def handle(self, *args, **options):
        project_uuid = options["project_uuid"]
        output_path = options["output"]
        expires_in = options["expires_in"]
        include_metadata = not options["no_metadata"]

        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist as exc:
            raise CommandError(f"Project with uuid '{project_uuid}' does not exist") from exc

        try:
            exporter = ContentFilesManifestExporter(
                project,
                expires_in=expires_in,
                include_metadata=include_metadata,
            )
            payload = exporter.export_json()
            manifest = exporter.build_manifest()
        except UnsupportedIndexerError as exc:
            raise CommandError(str(exc)) from exc

        with open(output_path, "w", encoding="utf-8") as output_file:
            output_file.write(payload)

        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {manifest['object_count']} presigned URLs for project "
                f"'{project.name}' ({project.uuid}) to {output_path}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                f"URLs expire at {manifest['expires_at']}. "
                "Run import_project_content_files in the destination environment before then."
            )
        )
