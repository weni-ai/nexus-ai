from django.core.exceptions import ValidationError
from django.test import TestCase

from nexus.projects.models import SpecializedKnowledgeEntry
from nexus.usecases.projects.specialized_knowledge import (
    create_specialized_knowledge_entry,
    retrieve_specialized_knowledge,
)
from nexus.usecases.projects.tests.project_factory import ProjectFactory


class SpecializedKnowledgeUseCaseTests(TestCase):
    def setUp(self):
        self.project = ProjectFactory(is_live_desk_copilot=True)
        self.other = ProjectFactory(is_live_desk_copilot=True)

    def test_create_and_retrieve_scopes_by_project(self):
        create_specialized_knowledge_entry(
            self.project,
            content="A nota fiscal da Smart TV LG é do pedido 02-956347009.",
            metadata={
                "room_uuid": "room-1",
                "category": "produto",
                "relevance": "current_issue",
                "demand": "2ª via da nota",
                "tags": ["nota fiscal"],
            },
        )
        create_specialized_knowledge_entry(
            self.other,
            content="A nota fiscal da outra loja é do pedido 99.",
            metadata={"category": "produto"},
        )

        results = retrieve_specialized_knowledge(
            project_uuid=str(self.project.uuid),
            query="nota fiscal smart tv",
        )

        self.assertEqual(len(results), 1)
        self.assertIn("02-956347009", results[0]["content"])
        self.assertEqual(results[0]["metadata"]["origin"], "agent")
        self.assertEqual(results[0]["metadata"]["category"], "produto")
        self.assertIn("room-1", results[0]["source"])
        self.assertGreater(results[0]["score"], 0)

    def test_filters_by_room_and_tags(self):
        create_specialized_knowledge_entry(
            self.project,
            content="O prazo de entrega para o CEP 01000 é de 3 dias.",
            metadata={"room_uuid": "room-a", "tags": ["entrega"], "category": "entrega"},
        )
        create_specialized_knowledge_entry(
            self.project,
            content="O prazo de entrega para o interior é de 8 dias.",
            metadata={"room_uuid": "room-b", "tags": ["entrega"], "category": "entrega"},
        )
        create_specialized_knowledge_entry(
            self.project,
            content="O prazo de entrega padrão da loja é de 5 dias.",
            metadata={"tags": ["entrega"], "category": "entrega"},
        )

        results = retrieve_specialized_knowledge(
            project_uuid=str(self.project.uuid),
            query="prazo de entrega",
            filters={"room_uuid": "room-a", "tags": ["entrega"]},
        )

        contents = [item["content"] for item in results]
        self.assertEqual(len(contents), 2)
        self.assertTrue(any("01000" in content for content in contents))
        self.assertTrue(any("padrão da loja" in content for content in contents))
        self.assertFalse(any("interior" in content for content in contents))

    def test_rejects_top_k_outside_contract(self):
        with self.assertRaises(ValueError):
            retrieve_specialized_knowledge(project_uuid=str(self.project.uuid), query="nota", top_k=0)
        with self.assertRaises(ValueError):
            retrieve_specialized_knowledge(project_uuid=str(self.project.uuid), query="nota", top_k=100)

    def test_rejects_invalid_category(self):
        with self.assertRaises(ValidationError):
            create_specialized_knowledge_entry(
                self.project,
                content="fato",
                metadata={"category": "nao-existe"},
            )
        self.assertEqual(SpecializedKnowledgeEntry.objects.count(), 0)

    def test_save_fills_blank_source(self):
        entry = SpecializedKnowledgeEntry(
            project=self.project,
            content="O prazo de troca é de 7 dias.",
            room_uuid="room-9",
        )
        entry.full_clean()
        entry.save()
        self.assertIn("room-9", entry.source)
        self.assertEqual(entry.origin, "agent")

    def test_rejects_normal_project(self):
        normal = ProjectFactory(is_live_desk_copilot=False)
        with self.assertRaises(ValidationError):
            create_specialized_knowledge_entry(normal, content="fato")

        entry = SpecializedKnowledgeEntry(project=normal, content="fato")
        with self.assertRaises(ValidationError):
            entry.full_clean()
