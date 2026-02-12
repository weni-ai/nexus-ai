import json

from django.core.management.base import BaseCommand
from django.core.serializers.json import DjangoJSONEncoder
from django.db.models import Prefetch

from nexus.intelligences.models import SubTopics, Topics


class Command(BaseCommand):
    help = "Exporta os dados das tabelas Topics e SubTopics para JSON"

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            type=str,
            default="topics_export.json",
            help="Nome do arquivo de saída (padrão: topics_export.json)",
        )
        parser.add_argument(
            "--project-uuid", type=str, default=None, help="UUID do projeto para filtrar os dados (opcional)"
        )

    def handle(self, *args, **options):
        output_file = options["output"]
        project_uuid = options.get("project_uuid")

        # Prepara a query com prefetch para otimizar
        topics_query = Topics.objects.select_related("project").prefetch_related(
            Prefetch("subtopics", queryset=SubTopics.objects.all())
        )

        # Filtra por projeto se fornecido
        if project_uuid:
            topics_query = topics_query.filter(project__uuid=project_uuid)

        # Serializa os dados
        topics_data = []
        subtopics_data = []

        for topic in topics_query:
            # Dados do Topic
            topic_dict = {
                "uuid": str(topic.uuid),
                "name": topic.name,
                "description": topic.description,
                "created_at": topic.created_at.isoformat() if topic.created_at else None,
                "project_uuid": str(topic.project.uuid) if topic.project else None,
            }
            topics_data.append(topic_dict)

            # Dados dos SubTopics relacionados
            for subtopic in topic.subtopics.all():
                subtopic_dict = {
                    "uuid": str(subtopic.uuid),
                    "name": subtopic.name,
                    "description": subtopic.description,
                    "created_at": subtopic.created_at.isoformat() if subtopic.created_at else None,
                    "topic_uuid": str(topic.uuid),
                }
                subtopics_data.append(subtopic_dict)

        # Estrutura final do JSON
        export_data = {
            "topics": topics_data,
            "subtopics": subtopics_data,
            "metadata": {
                "total_topics": len(topics_data),
                "total_subtopics": len(subtopics_data),
                "exported_at": json.loads(
                    json.dumps(topics_data[0]["created_at"] if topics_data else None, cls=DjangoJSONEncoder)
                )
                if topics_data
                else None,
            },
        }

        # Salva o arquivo JSON
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump(export_data, f, indent=2, ensure_ascii=False, cls=DjangoJSONEncoder)

        self.stdout.write(
            self.style.SUCCESS(
                f"✓ Exportação concluída!\n"
                f"  - Arquivo: {output_file}\n"
                f"  - Topics exportados: {len(topics_data)}\n"
                f"  - SubTopics exportados: {len(subtopics_data)}"
            )
        )
