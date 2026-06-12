from django.core.management.base import BaseCommand, CommandError

from nexus.projects.services.project_transfer.content_files_manifest import ContentFilesManifestImporter


class Command(BaseCommand):
    help = (
        "Download Bedrock content base files from presigned URLs in a manifest "
        "and upload them to the destination bucket using the same S3 keys"
    )

    def add_arguments(self, parser):
        parser.add_argument("--input", required=True, help="Path to the manifest JSON from export_project_content_files")
        parser.add_argument("--dest-bucket", required=True, help="Destination S3 bucket name")
        parser.add_argument(
            "--dest-region",
            default=None,
            help="Destination AWS region (default: AWS_BEDROCK_REGION_NAME from settings)",
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
        dest_bucket = options["dest_bucket"]
        dest_region = options["dest_region"]
        skip_existing = options["skip_existing"]
        dry_run = options["dry_run"]

        with open(input_path, encoding="utf-8") as input_file:
            raw = input_file.read()

        try:
            importer = ContentFilesManifestImporter.from_json(
                raw,
                dest_bucket=dest_bucket,
                dest_region=dest_region,
                skip_existing=skip_existing,
                dry_run=dry_run,
            )
            result = importer.import_files()
        except ValueError as exc:
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
