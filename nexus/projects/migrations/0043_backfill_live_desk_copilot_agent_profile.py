from django.db import migrations
from django.db.models import Q

# Frozen copy of the copilot agent profile. Do not import live_desk_copilot:
# a later edit of those constants must not change what this backfill wrote.
_NAME = "Desk Copilot"
_ROLE = "Human Rep Copilot"
_GOAL = "Make the human representative faster and more accurate in every customer conversation."
_PERSONALITY = "friendly"


def forwards_blank_copilot_agents(apps, schema_editor):
    """Fill name, role, goal, and tone on copilot agents that were never configured."""
    ContentBaseAgent = apps.get_model("intelligences", "ContentBaseAgent")
    ContentBaseAgent.objects.filter(
        content_base__is_router=True,
        content_base__intelligence__integratedintelligence__project__is_live_desk_copilot=True,
    ).filter(Q(name__isnull=True) | Q(name="")).update(
        name=_NAME,
        role=_ROLE,
        goal=_GOAL,
        personality=_PERSONALITY,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0042_specializedknowledgeentry"),
        ("intelligences", "0032_instructioncategory_and_category_fk"),
    ]

    operations = [
        migrations.RunPython(forwards_blank_copilot_agents, migrations.RunPython.noop),
    ]
