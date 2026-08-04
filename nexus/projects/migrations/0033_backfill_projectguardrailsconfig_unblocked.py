# Generated manually for guardrails defaults backfill

from django.db import migrations
from django.utils import timezone


_BACKFILL_SLUGS = [
    "politics",
    "physical_health",
    "sexual_content",
    "bias",
    "hate",
    "religion",
    "suicide",
    "self_harm",
    "beliefs",
    "gender_identity",
    "sexual_relations",
]


def forwards_backfill_existing_projects_unblocked(apps, schema_editor):
    """
    Existing projects get an explicit config with all categories unblocked.
    Projects created after this migration use code defaults (all blocked) on first init.
    """
    Project = apps.get_model("projects", "Project")
    ProjectGuardrailsConfig = apps.get_model("projects", "ProjectGuardrailsConfig")

    unblocked_states = {slug: False for slug in _BACKFILL_SLUGS}
    existing_project_ids = set(ProjectGuardrailsConfig.objects.values_list("project_id", flat=True))
    now = timezone.now()
    batch = []

    for project_id in (
        Project.objects.filter(is_active=True).values_list("uuid", flat=True).iterator(chunk_size=500)
    ):
        if project_id in existing_project_ids:
            continue
        batch.append(
            ProjectGuardrailsConfig(
                project_id=project_id,
                category_states=unblocked_states,
                blocking_message=None,
                initialized_as_new_project=False,
                bedrock_guardrail_pool=None,
                bedrock_guardrail_identifier=None,
                bedrock_guardrail_version=None,
                created_on=now,
                modified_on=now,
            )
        )
        if len(batch) >= 500:
            ProjectGuardrailsConfig.objects.bulk_create(batch)
            batch = []

    if batch:
        ProjectGuardrailsConfig.objects.bulk_create(batch)


def backwards_noop(apps, schema_editor):
    # Keep backfilled rows; removing them would reintroduce ambiguous defaults.
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0032_bedrockguardrailpool"),
    ]

    operations = [
        migrations.RunPython(forwards_backfill_existing_projects_unblocked, backwards_noop),
    ]
