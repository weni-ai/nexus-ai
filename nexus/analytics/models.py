from uuid import uuid4

from django.db import models


class InlineAgentLatencyHourly(models.Model):
    """Hourly rollup for inline agent turn latency (Plan B)."""

    project_uuid = models.UUIDField(db_index=True)
    hour_ts = models.DateTimeField(db_index=True)
    execution_path = models.CharField(max_length=64, default="inline_agents")
    phase = models.CharField(max_length=64)
    turn_count = models.PositiveIntegerField(default=0)
    sum_ms = models.BigIntegerField(default=0)
    max_ms = models.PositiveIntegerField(default=0)
    buckets = models.JSONField(default=dict, blank=True)
    error_count = models.PositiveIntegerField(default=0)
    blocked_count = models.PositiveIntegerField(default=0)
    schema_version = models.PositiveSmallIntegerField(default=1)

    class Meta:
        db_table = "inline_agent_latency_hourly"
        constraints = [
            models.UniqueConstraint(
                fields=("project_uuid", "hour_ts", "execution_path", "phase"),
                name="inline_agent_latency_hourly_uniq",
            ),
        ]
        indexes = [
            models.Index(fields=["project_uuid", "hour_ts"]),
        ]


class InlineAgentTurnOutlier(models.Model):
    """Slow, failed, or sampled turns for drill-down."""

    id = models.UUIDField(primary_key=True, default=uuid4, editable=False)
    project_uuid = models.UUIDField(db_index=True)
    execution_path = models.CharField(max_length=64, default="inline_agents")
    turn_finished_at = models.DateTimeField(db_index=True)
    contact_urn = models.CharField(max_length=512)
    turn_id = models.CharField(max_length=255)
    message_conversation_log_uuid = models.UUIDField(null=True, blank=True)
    channel_type = models.CharField(max_length=32, blank=True, default="")
    celery_task_id = models.CharField(max_length=255, blank=True, default="")
    status = models.CharField(max_length=32)
    total_ms = models.PositiveIntegerField()
    boundaries_ms = models.JSONField(default=dict, blank=True)
    phase_ms = models.JSONField(default=dict, blank=True)
    context = models.JSONField(default=dict, blank=True)
    router_received_at = models.DateTimeField(null=True, blank=True)
    sample_reason = models.CharField(max_length=32)
    schema_version = models.PositiveSmallIntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)

    def to_api_dict(self) -> dict:
        from nexus.analytics.latency_conversation_lookup import build_conversation_lookup

        return {
            "id": str(self.id),
            "turn_finished_at": self.turn_finished_at.isoformat().replace("+00:00", "Z"),
            "contact_urn": self.contact_urn,
            "turn_id": self.turn_id,
            "message_conversation_log_uuid": str(self.message_conversation_log_uuid)
            if self.message_conversation_log_uuid
            else None,
            "channel_type": self.channel_type,
            "celery_task_id": self.celery_task_id,
            "status": self.status,
            "total_ms": self.total_ms,
            "boundaries_ms": self.boundaries_ms,
            "phase_ms": self.phase_ms,
            "sample_reason": self.sample_reason,
            "conversation_lookup": build_conversation_lookup(
                project_uuid=str(self.project_uuid),
                contact_urn=self.contact_urn,
                turn_finished_at=self.turn_finished_at,
                turn_id=self.turn_id,
            ),
        }

    class Meta:
        db_table = "inline_agent_turn_outlier"
        indexes = [
            models.Index(fields=["project_uuid", "-turn_finished_at"]),
            models.Index(fields=["project_uuid", "-total_ms"]),
        ]
