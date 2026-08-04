"""Initial inline agent latency storage models (Plan B)."""

import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="InlineAgentLatencyHourly",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("project_uuid", models.UUIDField(db_index=True)),
                ("hour_ts", models.DateTimeField(db_index=True)),
                ("execution_path", models.CharField(default="inline_agents", max_length=64)),
                ("phase", models.CharField(max_length=64)),
                ("turn_count", models.PositiveIntegerField(default=0)),
                ("sum_ms", models.BigIntegerField(default=0)),
                ("max_ms", models.PositiveIntegerField(default=0)),
                ("buckets", models.JSONField(blank=True, default=dict)),
                ("error_count", models.PositiveIntegerField(default=0)),
                ("blocked_count", models.PositiveIntegerField(default=0)),
                ("schema_version", models.PositiveSmallIntegerField(default=1)),
            ],
            options={
                "db_table": "inline_agent_latency_hourly",
            },
        ),
        migrations.CreateModel(
            name="InlineAgentTurnOutlier",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("project_uuid", models.UUIDField(db_index=True)),
                ("execution_path", models.CharField(default="inline_agents", max_length=64)),
                ("turn_finished_at", models.DateTimeField(db_index=True)),
                ("contact_urn", models.CharField(max_length=512)),
                ("turn_id", models.CharField(max_length=255)),
                ("message_conversation_log_uuid", models.UUIDField(blank=True, null=True)),
                ("channel_type", models.CharField(blank=True, default="", max_length=32)),
                ("celery_task_id", models.CharField(blank=True, default="", max_length=255)),
                ("status", models.CharField(max_length=32)),
                ("total_ms", models.PositiveIntegerField()),
                ("boundaries_ms", models.JSONField(blank=True, default=dict)),
                ("phase_ms", models.JSONField(blank=True, default=dict)),
                ("context", models.JSONField(blank=True, default=dict)),
                ("router_received_at", models.DateTimeField(blank=True, null=True)),
                ("sample_reason", models.CharField(max_length=32)),
                ("schema_version", models.PositiveSmallIntegerField(default=1)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "db_table": "inline_agent_turn_outlier",
            },
        ),
        migrations.AddConstraint(
            model_name="inlineagentlatencyhourly",
            constraint=models.UniqueConstraint(
                fields=("project_uuid", "hour_ts", "execution_path", "phase"),
                name="inline_agent_latency_hourly_uniq",
            ),
        ),
        migrations.AddIndex(
            model_name="inlineagentlatencyhourly",
            index=models.Index(fields=["project_uuid", "hour_ts"], name="inline_agent_project_hour_idx"),
        ),
        migrations.AddIndex(
            model_name="inlineagentturnoutlier",
            index=models.Index(fields=["project_uuid", "-turn_finished_at"], name="inline_agent_outlier_time_idx"),
        ),
        migrations.AddIndex(
            model_name="inlineagentturnoutlier",
            index=models.Index(fields=["project_uuid", "-total_ms"], name="inline_agent_outlier_slow_idx"),
        ),
    ]
