from django.core.management.base import BaseCommand, CommandError

from nexus.projects.services.project_transfer.traces_files_collector import MissingTracesBucketError
from nexus.projects.services.project_transfer.traces_files_manifest import TraceFilesManifestImporter


class Command(BaseCommand):
    help = (
        "Download inline trace files from presigned URLs in a manifest and upload them "
        "to AWS_BEDROCK_INLINE_TRACES_BUCKET using the same keys as get_inline_traces "
        "(optionally remapped to a new project UUID)"
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--input",
            required=True,
            help="Path to the manifest JSON from export_project_trace_files",
        )
        parser.add_argument(
            "--dest-inline-bucket",
            default=None,
            help="Destination bucket for inline traces (default: AWS_BEDROCK_INLINE_TRACES_BUCKET)",
        )
        parser.add_argument(
            "--dest-legacy-bucket",
            default=None,
            help="Destination bucket for legacy traces (default: AWS_BEDROCK_BUCKET_NAME)",
        )
        parser.add_argument(
            "--dest-inline-region",
            default=None,
            help="Destination AWS region for inline traces (default: AWS_BEDROCK_INLINE_TRACES_REGION)",
        )
        parser.add_argument(
            "--dest-legacy-region",
            default=None,
            help="Destination AWS region for legacy traces (default: AWS_BEDROCK_REGION_NAME)",
        )
        parser.add_argument(
            "--dest-project-uuid",
            default=None,
            help="Rewrite trace keys to use this project UUID instead of the one from the export",
        )
        parser.add_argument(
            "--skip-existing",
            action="store_true",
            help="Skip objects that already exist in the destination bucket",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="List objects that would be copied without downloading or uploading",
        )

    def handle(self, *args, **options):
        input_path = options["input"]
        dest_inline_bucket = options["dest_inline_bucket"]
        dest_legacy_bucket = options["dest_legacy_bucket"]
        dest_inline_region = options["dest_inline_region"]
        dest_legacy_region = options["dest_legacy_region"]
        dest_project_uuid = options["dest_project_uuid"]
        skip_existing = options["skip_existing"]
        dry_run = options["dry_run"]

        with open(input_path, encoding="utf-8") as input_file:
            raw = input_file.read()

        try:
            importer = TraceFilesManifestImporter.from_json(
                raw,
                dest_inline_bucket=dest_inline_bucket,
                dest_legacy_bucket=dest_legacy_bucket,
                dest_inline_region=dest_inline_region,
                dest_legacy_region=dest_legacy_region,
                dest_project_uuid=dest_project_uuid,
                skip_existing=skip_existing,
                dry_run=dry_run,
            )
            result = importer.import_files()
        except (ValueError, MissingTracesBucketError) as exc:
            raise CommandError(str(exc)) from exc

        stats = result["stats"]
        if dry_run:
            self.stdout.write(self.style.WARNING("Dry run completed. No files were transferred."))

        self.stdout.write(
            self.style.SUCCESS(
                f"Processed {stats['total']} objects: "
                f"{stats['copied']} copied, {stats['skipped']} skipped, {stats['failed']} failed"
            )
        )

        for error in result["errors"]:
            self.stdout.write(self.style.ERROR(error))

        if stats["failed"]:
            raise CommandError(f"{stats['failed']} object(s) failed to import")
