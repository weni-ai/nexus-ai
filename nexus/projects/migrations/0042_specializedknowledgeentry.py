import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("projects", "0041_project_timezone"),
    ]

    operations = [
        migrations.CreateModel(
            name="SpecializedKnowledgeEntry",
            fields=[
                ("uuid", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("content", models.TextField()),
                ("source", models.CharField(blank=True, max_length=512)),
                ("room_uuid", models.CharField(blank=True, max_length=64)),
                ("origin", models.CharField(choices=[("agent", "agent")], default="agent", max_length=32)),
                ("demand", models.TextField(blank=True)),
                (
                    "category",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("pedido", "pedido"),
                            ("entrega", "entrega"),
                            ("pagamento", "pagamento"),
                            ("produto", "produto"),
                            ("conta", "conta"),
                            ("preferencia", "preferencia"),
                            ("contato", "contato"),
                            ("politica", "politica"),
                            ("procedimento", "procedimento"),
                            ("outro", "outro"),
                        ],
                        max_length=32,
                    ),
                ),
                (
                    "relevance",
                    models.CharField(
                        blank=True,
                        choices=[("current_issue", "current_issue"), ("likely_future_issue", "likely_future_issue")],
                        max_length=32,
                    ),
                ),
                ("tags", models.JSONField(blank=True, default=list)),
                ("created_on", models.DateTimeField(auto_now_add=True)),
                (
                    "project",
                    models.ForeignKey(
                        limit_choices_to={"is_live_desk_copilot": True},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="specialized_knowledge_entries",
                        to="projects.project",
                    ),
                ),
            ],
        ),
        migrations.AddIndex(
            model_name="specializedknowledgeentry",
            index=models.Index(fields=["project", "category"], name="projects_sp_project_7a0c0d_idx"),
        ),
        migrations.AddIndex(
            model_name="specializedknowledgeentry",
            index=models.Index(fields=["project", "relevance"], name="projects_sp_project_1b6e2a_idx"),
        ),
        migrations.AddIndex(
            model_name="specializedknowledgeentry",
            index=models.Index(fields=["project", "room_uuid"], name="projects_sp_project_9c4f11_idx"),
        ),
    ]
