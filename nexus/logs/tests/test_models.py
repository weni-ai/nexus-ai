from django.test import TestCase

from nexus.usecases.intelligences.tests.intelligence_factory import IntelligenceFactory
from nexus.usecases.projects.tests.project_factory import ProjectFactory

from ..models import (
    RecentActivities,
)


class TestRecentActivities(TestCase):
    def setUp(self) -> None:
        self.project = ProjectFactory()
        self.intelligence = IntelligenceFactory(created_by=self.project.created_by, org=self.project.org)

    def test_create_recent_activities(self):
        recent_activities = RecentActivities.objects.create(
            action_model="model",
            action_type="C",
            project=self.project,
            created_by=self.project.created_by,
            intelligence=self.intelligence,
        )
        self.assertEqual(recent_activities.action_model, "model")
        self.assertEqual(recent_activities.action_type, "C")
        self.assertEqual(recent_activities.project, self.project)
        self.assertEqual(recent_activities.created_by, self.project.created_by)
        self.assertEqual(recent_activities.intelligence, self.intelligence)
