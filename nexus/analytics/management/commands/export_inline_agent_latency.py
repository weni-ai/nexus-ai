"""Export inline agent latency data older than retention window (stub for cold storage)."""

from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from nexus.analytics.models import InlineAgentLatencyHourly, InlineAgentTurnOutlier

RETENTION_DAYS = 90


class Command(BaseCommand):
    help = "Export and delete inline agent latency rows older than the retention window."

    def handle(self, *args, **options):
        cutoff = timezone.now() - timedelta(days=RETENTION_DAYS)
        hourly_qs = InlineAgentLatencyHourly.objects.filter(hour_ts__lt=cutoff)
        outlier_qs = InlineAgentTurnOutlier.objects.filter(turn_finished_at__lt=cutoff)
        hourly_count = hourly_qs.count()
        outlier_count = outlier_qs.count()

        if hourly_count == 0 and outlier_count == 0:
            self.stdout.write("No inline agent latency rows to export.")
            return

        self.stdout.write(
            self.style.WARNING(
                f"Found {hourly_count} hourly rollup rows and {outlier_count} outlier rows before {cutoff.isoformat()}. "
                "S3/Parquet export is not implemented yet — skipping delete to avoid data loss."
            )
        )
