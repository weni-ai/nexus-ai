# Existing projects at prompt-injection-filter deploy stay disabled.
# Projects created after this migration get True via get_or_initialize defaults.

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


def forwards_existing_projects_filter_off(apps, schema_editor):
    """
    At deploy: every existing project keeps prompt_injection_filter_enabled=False.
    - Rows already present: force False (AddField default is already False).
    - Active projects still missing a config row: create unblocked legacy defaults
      with filter off (same pattern as 0033), so first lazy-init after deploy does
      not treat them as "new" (True).
    """
    Project = apps.get_model("projects", "Project")
    ProjectGuardrailsConfig = apps.get_model("projects", "ProjectGuardrailsConfig")

    ProjectGuardrailsConfig.objects.update(prompt_injection_filter_enabled=False)

    unblocked_states = {slug: False for slug in _BACKFILL_SLUGS}
    existing_ids_qs = ProjectGuardrailsConfig.objects.values_list("project_id", flat=True)
    now = timezone.now()
    batch = []

    for project_id in (
        Project.objects.filter(is_active=True)
        .exclude(uuid__in=existing_ids_qs)
        .values_list("uuid", flat=True)
        .iterator(chunk_size=500)
    ):
        batch.append(
            ProjectGuardrailsConfig(
                project_id=project_id,
                category_states=unblocked_states,
                blocking_message=None,
                prompt_injection_filter_enabled=False,
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
    pass


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0034_project_is_live_desk_copilot"),
    ]

    operations = [
        migrations.RunPython(forwards_existing_projects_filter_off, backwards_noop),
    ]
