"""Seed Whirlpool ManagerAgent + ModelProvider for the custom-model PoC.

Usage:
    poetry run python manage.py seed_whirlpool_model_provider

Then activate credentials for a project via the model-providers API with:
    client_id / client_secret (and optional token_url, generate_content_url, api_base).

Local fallback: WHIRLPOOL_CLIENT_ID / WHIRLPOOL_CLIENT_SECRET env vars.
"""

from django.core.management.base import BaseCommand
from django.utils import timezone

from inline_agents.backends.openai.custom_providers.whirlpool import (
    WHIRLPOOL_CREDENTIAL_SCHEMA,
    WHIRLPOOL_MODEL_ID,
)
from nexus.inline_agents.backends.openai.models import ManagerAgent, ModelProvider


class Command(BaseCommand):
    help = "Seed Whirlpool ManagerAgent and ModelProvider for the custom Model PoC"

    def handle(self, *args, **options):
        manager, manager_created = ManagerAgent.objects.update_or_create(
            name="Whirlpool Manager (PoC)",
            defaults={
                "base_prompt": "You are a helpful assistant.",
                "foundation_model": WHIRLPOOL_MODEL_ID,
                "model_vendor": "whirlpool",
                "model_has_reasoning": False,
                "max_tokens": 2048,
                "collaborator_max_tokens": 2048,
                "parallel_tool_calls": False,
                "tools": [],
                "knowledge_bases": [],
                "formatter_agent_foundation_model": WHIRLPOOL_MODEL_ID,
                "formatter_agent_model_has_reasoning": False,
                "formatter_agent_prompt": "",
                "collaborators_foundation_model": WHIRLPOOL_MODEL_ID,
                "override_collaborators_foundation_model": True,
                "default_instructions_for_collaborators": "",
                "default": False,
                "public": True,
                "release_date": timezone.now(),
            },
        )

        provider, provider_created = ModelProvider.objects.update_or_create(
            model_vendor="whirlpool",
            defaults={
                "label": "Whirlpool",
                "credentials": WHIRLPOOL_CREDENTIAL_SCHEMA,
                "manager_agent": manager,
            },
        )

        self.stdout.write(
            self.style.SUCCESS(
                f"ManagerAgent {'created' if manager_created else 'updated'}: "
                f"{manager.name} uuid={manager.uuid} model={manager.foundation_model}"
            )
        )
        self.stdout.write(
            self.style.SUCCESS(
                f"ModelProvider {'created' if provider_created else 'updated'}: "
                f"{provider.label} vendor={provider.model_vendor}"
            )
        )
        self.stdout.write(
            "Assign this provider to a project and set client_id/client_secret "
            "(or use WHIRLPOOL_CLIENT_ID / WHIRLPOOL_CLIENT_SECRET)."
        )
