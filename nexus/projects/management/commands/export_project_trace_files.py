import json

from django.core.management.base import BaseCommand, CommandError

from nexus.projects.models import Project
from nexus.projects.services.project_transfer.traces_files_collector import MissingTracesBucketError
from nexus.projects.services.project_transfer.traces_files_constants import DEFAULT_PRESIGNED_URL_EXPIRATION_SECONDS
from nexus.projects.services.project_transfer.traces_files_manifest import TraceFilesManifestExporter


class Command(BaseCommand):
    help = (
        "Export presigned download URLs for inline agent trace files "
        "(inline_traces/{project_uuid}/{message_uuid}.jsonl — same path as get_inline_traces) "
        "to a manifest JSON"
    )

    def add_arguments(self, parser):
        parser.add_argument("--project-uuid", required=True, help="UUID of the project")
        parser.add_argument("--output", required=True, help="Path to the output manifest JSON file")
        parser.add_argument(
            "--expires-in",
            type=int,
            default=DEFAULT_PRESIGNED_URL_EXPIRATION_SECONDS,
            help="Presigned URL expiration in seconds (default: 86400)",
        )
        parser.add_argument(
            "--include-legacy",
            action="store_true",
            help="Also include legacy traces/ prefix files from AgentMessage (get_traces)",
        )

    def handle(self, *args, **options):
        project_uuid = options["project_uuid"]
        output_path = options["output"]
        expires_in = options["expires_in"]
        include_inline = True
        include_legacy = options["include_legacy"]

        try:
            project = Project.objects.get(uuid=project_uuid)
        except Project.DoesNotExist as exc:
            raise CommandError(f"Project with uuid '{project_uuid}' does not exist") from exc

        try:
            exporter = TraceFilesManifestExporter(
                project,
                expires_in=expires_in,
                include_inline=include_inline,
                include_legacy=include_legacy,
            )
            manifest = exporter.build_manifest()
        except MissingTracesBucketError as exc:
            raise CommandError(str(exc)) from exc

        payload = json.dumps(manifest, indent=2, ensure_ascii=False)

        with open(output_path, "w", encoding="utf-8") as output_file:
            output_file.write(payload)

        self.stdout.write(
            self.style.SUCCESS(
                f"Exported {manifest['object_count']} trace presigned URLs for project "
                f"'{project.name}' ({project.uuid}) to {output_path}"
            )
        )
        self.stdout.write(
            self.style.WARNING(
                f"URLs expire at {manifest['expires_at']}. "
                "Run import_project_trace_files in the destination environment before then."
            )
        )
