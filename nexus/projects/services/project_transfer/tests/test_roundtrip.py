from __future__ import annotations

import json
import tempfile
from io import StringIO
from uuid import uuid4

from django.core.management import call_command
from django.test import TestCase

from nexus.inline_agents.models import Agent, InlineAgentsConfiguration, Version
from nexus.intelligences.models import ContentBase, IntegratedIntelligence, Intelligence
from nexus.orgs.models import Org
from nexus.projects.models import Channel, IntegratedFeature, Project
from nexus.projects.services.project_transfer.exporter import ProjectExporter
from nexus.projects.services.project_transfer.importer import ProjectImporter
from nexus.usecases.intelligences.tests.intelligence_factory import (
    ContentBaseFactory,
    IntegratedIntelligenceFactory,
    LLMFactory,
)
from nexus.usecases.projects.tests.project_factory import IntegratedFeatureFactory, ProjectFactory
from nexus.usecases.users.tests.user_factory import UserFactory


class ProjectTransferRoundtripTestCase(TestCase):
    def setUp(self):
        self.import_user = UserFactory(email="import-user@example.com")
        self.integrated_intelligence = IntegratedIntelligenceFactory()
        self.project = self.integrated_intelligence.project
        self.org = self.project.org
        self.llm = LLMFactory(
            integrated_intelligence=self.integrated_intelligence,
            created_by=self.project.created_by,
        )
        self.content_base = ContentBaseFactory(
            intelligence=self.integrated_intelligence.intelligence,
            created_by=self.project.created_by,
        )
        IntegratedFeatureFactory(project=self.project)

        self.agent = Agent.objects.create(
            project=self.project,
            name="Support Agent",
            slug="support-agent",
            instruction="Help users",
            collaboration_instructions="Collaborate",
        )
        Version.objects.create(
            agent=self.agent,
            skills=[{"name": "search"}],
            display_skills=[{"name": "search"}],
        )
        InlineAgentsConfiguration.objects.create(
            project=self.project,
            agents_backend="OpenAIBackend",
        )
        Channel.objects.create(
            uuid=uuid4(),
            project=self.project,
            channel_type="whatsapp",
            is_default_for_preview=True,
        )

        self.original_counts = {
            "orgs": Org.objects.filter(pk=self.org.pk).count(),
            "projects": Project.objects.filter(pk=self.project.pk).count(),
            "intelligences": Intelligence.objects.filter(org=self.org).count(),
            "content_bases": ContentBase.objects.filter(intelligence__org=self.org).count(),
            "inline_agents": Agent.objects.filter(project=self.project).count(),
            "integrated_features": IntegratedFeature.objects.filter(project=self.project).count(),
        }

    def test_exporter_collects_project_graph(self):
        exporter = ProjectExporter(self.project)
        bundle = exporter.export()

        self.assertEqual(bundle["source_project_uuid"], str(self.project.uuid))
        self.assertIn("orgs.Org", bundle["records"])
        self.assertIn("projects.Project", bundle["records"])
        self.assertIn("intelligences.ContentBase", bundle["records"])
        self.assertIn("inline_agents.Agent", bundle["records"])

    def test_roundtrip_via_service(self):
        exporter = ProjectExporter(self.project)
        bundle = exporter.export()

        project_uuid = self.project.uuid
        org_uuid = self.org.uuid
        agent_uuid = self.agent.uuid
        content_base_uuid = self.content_base.uuid

        Project.objects.filter(pk=self.project.pk).delete()
        Org.objects.filter(pk=self.org.pk).delete()

        importer = ProjectImporter(bundle, self.import_user.email)
        imported_project = importer.import_project()

        self.assertEqual(str(imported_project.uuid), str(project_uuid))
        self.assertTrue(Org.objects.filter(uuid=org_uuid).exists())
        self.assertTrue(Project.objects.filter(uuid=project_uuid).exists())
        self.assertTrue(ContentBase.objects.filter(uuid=content_base_uuid).exists())
        self.assertTrue(Agent.objects.filter(uuid=agent_uuid, project=imported_project).exists())
        self.assertEqual(
            IntegratedIntelligence.objects.filter(project=imported_project).count(),
            1,
        )
        self.assertEqual(
            IntegratedFeature.objects.filter(project=imported_project).count(),
            self.original_counts["integrated_features"],
        )

    def test_management_commands_roundtrip(self):
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as temp_file:
            output_path = temp_file.name

        call_command(
            "export_project",
            f"--project-uuid={self.project.uuid}",
            f"--output={output_path}",
            stdout=StringIO(),
        )

        project_uuid = self.project.uuid
        Project.objects.filter(pk=self.project.pk).delete()
        Org.objects.filter(pk=self.org.pk).delete()

        call_command(
            "import_project",
            f"--input={output_path}",
            f"--user-email={self.import_user.email}",
            stdout=StringIO(),
        )

        self.assertTrue(Project.objects.filter(uuid=project_uuid).exists())

    def test_import_project_dry_run_rolls_back(self):
        exporter = ProjectExporter(self.project)
        payload = json.dumps(exporter.export())

        Project.objects.filter(pk=self.project.pk).delete()
        Org.objects.filter(pk=self.org.pk).delete()

        importer = ProjectImporter.from_json(payload, self.import_user.email, dry_run=True)
        importer.import_project()

        self.assertFalse(Project.objects.filter(uuid=self.project.uuid).exists())
        self.assertFalse(Org.objects.filter(uuid=self.org.uuid).exists())

    def test_skip_if_exists_raises_when_project_present(self):
        exporter = ProjectExporter(self.project)
        payload = json.dumps(exporter.export())

        with self.assertRaises(ValueError):
            ProjectImporter.from_json(
                payload,
                self.import_user.email,
                skip_if_exists=True,
            ).import_project()
