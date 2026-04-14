from django.db import migrations


PROVIDERS = [
    {
        "label": "OpenAI",
        "model_vendor": "openai",
        "credentials": [
            {"id": "api_key", "label": "API key", "type": "PASSWORD"},
            {"id": "api_base", "label": "API base URL", "type": "TEXT"},
            {"id": "api_version", "label": "API version", "type": "TEXT"},
        ],
        "models": ["gpt-4o", "gpt-4o-mini", "gpt-4.1", "gpt-4.1-mini", "gpt-4.1-nano"],
    },
    {
        "label": "Azure OpenAI",
        "model_vendor": "azure",
        "credentials": [
            {"id": "api_key", "label": "API key", "type": "PASSWORD"},
            {"id": "api_base", "label": "Endpoint URL", "type": "TEXT"},
            {"id": "api_version", "label": "API version", "type": "TEXT"},
        ],
        "models": ["gpt-4o", "gpt-4o-mini"],
    },
    {
        "label": "Google Gemini",
        "model_vendor": "gemini",
        "credentials": [
            {"id": "api_key", "label": "API key", "type": "PASSWORD"},
        ],
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
    },
    {
        "label": "Vertex AI",
        "model_vendor": "vertex_ai",
        "credentials": [
            {"id": "service_account_json", "label": "Service account JSON", "type": "TEXTAREA"},
            {"id": "vertex_project", "label": "Project ID", "type": "TEXT"},
            {"id": "vertex_location", "label": "Location", "type": "TEXT"},
        ],
        "models": ["gemini-2.5-pro", "gemini-2.5-flash", "gemini-2.0-flash"],
    },
]


def seed_providers(apps, schema_editor):
    ModelProvider = apps.get_model("inline_agents", "ModelProvider")
    ManagerAgent = apps.get_model("inline_agents", "ManagerAgent")
    for provider_data in PROVIDERS:
        manager = ManagerAgent.objects.filter(model_vendor=provider_data["model_vendor"]).first()
        ModelProvider.objects.update_or_create(
            model_vendor=provider_data["model_vendor"],
            defaults={
                "label": provider_data["label"],
                "credentials": provider_data["credentials"],
                "models": provider_data["models"],
                "manager_agent": manager,
            },
        )


def reverse_seed(apps, schema_editor):
    ModelProvider = apps.get_model("inline_agents", "ModelProvider")
    vendors = [p["model_vendor"] for p in PROVIDERS]
    ModelProvider.objects.filter(model_vendor__in=vendors).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("inline_agents", "0029_modelprovider_projectmodelprovider"),
    ]

    operations = [
        migrations.RunPython(seed_providers, reverse_seed),
    ]
