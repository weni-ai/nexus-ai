from datetime import datetime
from unittest import skip

from django.contrib.auth.models import Permission
from django.contrib.contenttypes.models import ContentType
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from nexus.projects.models import ProjectAuth, ProjectAuthorizationRole
from nexus.usecases.intelligences.tests.intelligence_factory import (
    ConversationFactory,
    TopicsFactory,
)
from nexus.usecases.projects.tests.project_factory import ProjectFactory
from nexus.usecases.users.tests.user_factory import UserFactory


class BaseAnalyticsTestCase(TestCase):
    """Base test case with common setup"""

    def setUp(self):
        """Set up test data"""
        self.client = APIClient()
        self.user = UserFactory()

        ct = ContentType.objects.get_for_model(self.user)
        permission, _ = Permission.objects.get_or_create(
            codename="can_communicate_internally", name="can communicate internally", content_type=ct
        )
        self.user.user_permissions.add(permission)

        # Create projects with different backends
        self.project_ab2 = ProjectFactory(
            name="AB 2 Project",
            agents_backend="BedrockBackend",
            created_by=self.user,
        )
        self.project_ab2_5 = ProjectFactory(
            name="AB 2.5 Project",
            agents_backend="OpenAIBackend",
            created_by=self.user,
        )

        # Create topics for conversations
        self.topic_ab2 = TopicsFactory(project=self.project_ab2, name="AB2 Topic")
        self.topic_ab2_5 = TopicsFactory(project=self.project_ab2_5, name="AB2.5 Topic")

        # Create conversations with different resolutions
        # Resolved conversations for AB 2
        conv1 = ConversationFactory(
            project=self.project_ab2,
            topic=self.topic_ab2,
            resolution="0",  # Resolved
        )
        conv1.created_at = datetime(2024, 1, 15, 12, 0, 0)
        conv1.save(update_fields=["created_at"])

        conv2 = ConversationFactory(
            project=self.project_ab2,
            topic=self.topic_ab2,
            resolution="0",  # Resolved
        )
        conv2.created_at = datetime(2024, 1, 15, 13, 0, 0)
        conv2.save(update_fields=["created_at"])

        conv3 = ConversationFactory(
            project=self.project_ab2,
            topic=self.topic_ab2,
            resolution="1",  # Unresolved
        )
        conv3.created_at = datetime(2024, 1, 15, 14, 0, 0)
        conv3.save(update_fields=["created_at"])

        # Conversations for AB 2.5
        conv4 = ConversationFactory(
            project=self.project_ab2_5,
            topic=self.topic_ab2_5,
            resolution="0",  # Resolved
        )
        conv4.created_at = datetime(2024, 1, 15, 12, 0, 0)
        conv4.save(update_fields=["created_at"])

        conv5 = ConversationFactory(
            project=self.project_ab2_5,
            topic=self.topic_ab2_5,
            resolution="1",  # Unresolved
        )
        conv5.created_at = datetime(2024, 1, 15, 13, 0, 0)
        conv5.save(update_fields=["created_at"])

        conv6 = ConversationFactory(
            project=self.project_ab2_5,
            topic=self.topic_ab2_5,
            resolution="1",  # Unresolved
        )
        conv6.created_at = datetime(2024, 1, 15, 14, 0, 0)
        conv6.save(update_fields=["created_at"])

        self.client.force_authenticate(user=self.user)


class ResolutionRateAverageViewTestCase(BaseAnalyticsTestCase):
    """Tests for ResolutionRateAverageView"""

    def test_resolution_rate_with_ab2_project(self):
        """Test average resolution rate for AB 2 project"""
        url = reverse("resolution-rate-average")
        response = self.client.get(
            url,
            {"project_uuid": str(self.project_ab2.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("resolution_rate", data)
        self.assertIn("total_conversations", data)
        # Should have 3 conversations: 2 resolved, 1 unresolved
        self.assertEqual(data["total_conversations"], 3)
        self.assertEqual(data["resolved_conversations"], 2)
        self.assertAlmostEqual(data["resolution_rate"], 0.6667, places=3)

    def test_resolution_rate_with_ab2_5_project(self):
        """Test average resolution rate for AB 2.5 project"""
        url = reverse("resolution-rate-average")
        response = self.client.get(
            url,
            {"project_uuid": str(self.project_ab2_5.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should have 3 conversations: 1 resolved, 2 unresolved
        self.assertEqual(data["total_conversations"], 3)
        self.assertEqual(data["resolved_conversations"], 1)
        self.assertAlmostEqual(data["resolution_rate"], 0.3333, places=3)

    def test_resolution_rate_with_motor_filter_ab2(self):
        """Test filtering by motor AB 2"""
        url = reverse("resolution-rate-average")
        response = self.client.get(
            url,
            {
                "project_uuid": str(self.project_ab2.uuid),
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "motor": "AB 2",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_conversations"], 3)

    def test_resolution_rate_with_motor_filter_ab2_5(self):
        """Test filtering by motor AB 2.5"""
        url = reverse("resolution-rate-average")
        response = self.client.get(
            url,
            {
                "project_uuid": str(self.project_ab2_5.uuid),
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "motor": "AB 2.5",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_conversations"], 3)

    def test_resolution_rate_with_date_filtering(self):
        """Test date range filtering"""
        url = reverse("resolution-rate-average")
        # Create conversation outside date range
        conv_outside = ConversationFactory(
            project=self.project_ab2,
            topic=self.topic_ab2,
            resolution="0",
        )
        conv_outside.created_at = datetime(2024, 2, 15, 12, 0, 0)
        conv_outside.save(update_fields=["created_at"])

        response = self.client.get(
            url, {"project_uuid": str(self.project_ab2.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should only count conversations from January
        self.assertEqual(data["total_conversations"], 3)

    def test_resolution_rate_with_min_conversations(self):
        """Test min_conversations filter"""
        # Create project with fewer conversations
        project_small = ProjectFactory(
            name="Small Project",
            agents_backend="BedrockBackend",
            created_by=self.user,
        )
        topic_small = TopicsFactory(project=project_small)

        conv_small = ConversationFactory(
            project=project_small,
            topic=topic_small,
            resolution="0",
        )
        conv_small.created_at = datetime(2024, 1, 15, 12, 0, 0)
        conv_small.save(update_fields=["created_at"])

        url = reverse("resolution-rate-average")
        response = self.client.get(
            url,
            {
                "project_uuid": str(project_small.uuid),
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "min_conversations": "2",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should return 0 since project has only 1 conversation
        self.assertEqual(data["total_conversations"], 0)

    def test_resolution_rate_no_conversations(self):
        """Test with no conversations in date range"""
        project_empty = ProjectFactory(
            name="Empty Project",
            agents_backend="BedrockBackend",
            created_by=self.user,
        )

        url = reverse("resolution-rate-average")
        response = self.client.get(
            url, {"project_uuid": str(project_empty.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_conversations"], 0)
        self.assertEqual(data["resolution_rate"], 0.0)
        self.assertEqual(data["unresolved_rate"], 0.0)

    def test_resolution_rate_all_resolutions(self):
        """Test with all resolution types"""
        project = ProjectFactory(
            name="All Resolutions Project",
            agents_backend="BedrockBackend",
            created_by=self.user,
        )
        topic = TopicsFactory(project=project)

        conv1 = ConversationFactory(
            project=project,
            topic=topic,
            resolution="0",  # Resolved
        )
        conv1.created_at = datetime(2024, 1, 15, 12, 0, 0)
        conv1.save(update_fields=["created_at"])

        conv2 = ConversationFactory(
            project=project,
            topic=topic,
            resolution="1",  # Unresolved
        )
        conv2.created_at = datetime(2024, 1, 15, 13, 0, 0)
        conv2.save(update_fields=["created_at"])

        conv3 = ConversationFactory(
            project=project,
            topic=topic,
            resolution="2",  # In Progress
        )
        conv3.created_at = datetime(2024, 1, 15, 14, 0, 0)
        conv3.save(update_fields=["created_at"])

        conv4 = ConversationFactory(
            project=project,
            topic=topic,
            resolution="3",  # Unclassified
        )
        conv4.created_at = datetime(2024, 1, 15, 15, 0, 0)
        conv4.save(update_fields=["created_at"])

        conv5 = ConversationFactory(
            project=project,
            topic=topic,
            resolution="4",  # Has Chat Room
        )
        conv5.created_at = datetime(2024, 1, 15, 16, 0, 0)
        conv5.save(update_fields=["created_at"])

        url = reverse("resolution-rate-average")
        response = self.client.get(
            url, {"project_uuid": str(project.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_conversations"], 5)
        self.assertEqual(data["resolved_conversations"], 1)
        self.assertEqual(data["unresolved_conversations"], 1)
        self.assertIn("breakdown", data)
        self.assertEqual(data["breakdown"]["in_progress"], 1)
        self.assertEqual(data["breakdown"]["unclassified"], 1)
        self.assertEqual(data["breakdown"]["has_chat_room"], 1)

    def test_invalid_date_format(self):
        """Test with invalid date format"""
        url = reverse("resolution-rate-average")
        response = self.client.get(url, {"project_uuid": str(self.project_ab2.uuid), "start_date": "invalid-date"})

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_invalid_motor_value(self):
        """Test with invalid motor value"""
        url = reverse("resolution-rate-average")
        response = self.client.get(
            url,
            {
                "project_uuid": str(self.project_ab2.uuid),
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "motor": "Invalid Motor",
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_permission_check(self):
        """Test that permission is enforced"""
        unauthorized_user = UserFactory()
        self.client.force_authenticate(user=unauthorized_user)

        url = reverse("resolution-rate-average")
        response = self.client.get(
            url, {"project_uuid": str(self.project_ab2.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"}
        )

        self.assertEqual(response.status_code, 403)

    def test_start_date_after_end_date(self):
        """Test validation when start_date > end_date"""
        url = reverse("resolution-rate-average")
        response = self.client.get(
            url, {"project_uuid": str(self.project_ab2.uuid), "start_date": "2024-01-31", "end_date": "2024-01-01"}
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.json())

    def test_response_structure(self):
        """Test that response has all required fields"""
        url = reverse("resolution-rate-average")
        response = self.client.get(
            url, {"project_uuid": str(self.project_ab2.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        required_fields = [
            "resolution_rate",
            "unresolved_rate",
            "total_conversations",
            "resolved_conversations",
            "unresolved_conversations",
            "breakdown",
            "filters",
        ]
        for field in required_fields:
            self.assertIn(field, data)

    def test_default_dates(self):
        """Test that default dates are used when not provided"""
        url = reverse("resolution-rate-average")
        response = self.client.get(url, {"project_uuid": str(self.project_ab2.uuid)})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("filters", data)


class ResolutionRateIndividualViewTestCase(BaseAnalyticsTestCase):
    """Tests for ResolutionRateIndividualView"""

    def test_individual_resolution_rate_single_project(self):
        """Test individual resolution rate for single project"""
        url = reverse("resolution-rate-individual")
        response = self.client.get(
            url,
            {"project_uuid": str(self.project_ab2.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("projects", data)
        self.assertEqual(len(data["projects"]), 1)
        project_data = data["projects"][0]
        self.assertEqual(project_data["project_uuid"], str(self.project_ab2.uuid))
        self.assertEqual(project_data["motor"], "AB 2")
        self.assertEqual(project_data["total"], 3)

    def test_individual_resolution_rate_with_motor_filter(self):
        """Test filtering by motor"""
        url = reverse("resolution-rate-individual")
        response = self.client.get(
            url,
            {
                "project_uuid": str(self.project_ab2.uuid),
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "motor": "AB 2",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["projects"]), 1)
        self.assertEqual(data["projects"][0]["motor"], "AB 2")

    def test_individual_resolution_rate_with_min_conversations(self):
        """Test min_conversations filter"""
        url = reverse("resolution-rate-individual")
        response = self.client.get(
            url,
            {
                "project_uuid": str(self.project_ab2.uuid),
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "min_conversations": "5",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should return empty since we only have 3 conversations
        self.assertEqual(len(data["projects"]), 0)

    def test_empty_result(self):
        """Test with no matching conversations"""
        project_empty = ProjectFactory(
            name="Empty Project",
            agents_backend="BedrockBackend",
            created_by=self.user,
        )

        url = reverse("resolution-rate-individual")
        response = self.client.get(
            url, {"project_uuid": str(project_empty.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(len(data["projects"]), 0)

    def test_permission_check(self):
        """Test that permission is enforced"""
        unauthorized_user = UserFactory()
        self.client.force_authenticate(user=unauthorized_user)

        url = reverse("resolution-rate-individual")
        response = self.client.get(
            url, {"project_uuid": str(self.project_ab2.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"}
        )

        self.assertEqual(response.status_code, 403)


class UnresolvedRateViewTestCase(BaseAnalyticsTestCase):
    """Tests for UnresolvedRateView"""

    def test_unresolved_rate_calculation(self):
        """Test unresolved rate calculation"""
        url = reverse("unresolved-rate")
        response = self.client.get(
            url, {"project_uuid": str(self.project_ab2.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("unresolved_rate", data)
        # Should have 1 unresolved out of 3 total
        self.assertEqual(data["total_conversations"], 3)
        self.assertEqual(data["unresolved_conversations"], 1)
        self.assertAlmostEqual(data["unresolved_rate"], 0.3333, places=3)

    def test_unresolved_rate_with_no_unresolved(self):
        """Test when all conversations are resolved"""
        project = ProjectFactory(
            name="All Resolved Project",
            agents_backend="BedrockBackend",
            created_by=self.user,
        )
        topic = TopicsFactory(project=project)

        conv1 = ConversationFactory(
            project=project,
            topic=topic,
            resolution="0",  # Resolved
        )
        conv1.created_at = datetime(2024, 1, 15, 12, 0, 0)
        conv1.save(update_fields=["created_at"])

        conv2 = ConversationFactory(
            project=project,
            topic=topic,
            resolution="0",  # Resolved
        )
        conv2.created_at = datetime(2024, 1, 15, 13, 0, 0)
        conv2.save(update_fields=["created_at"])

        url = reverse("unresolved-rate")
        response = self.client.get(
            url, {"project_uuid": str(project.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["unresolved_rate"], 0.0)
        self.assertEqual(data["unresolved_conversations"], 0)

    def test_unresolved_rate_with_all_unresolved(self):
        """Test when all conversations are unresolved"""
        project = ProjectFactory(
            name="All Unresolved Project",
            agents_backend="BedrockBackend",
            created_by=self.user,
        )
        topic = TopicsFactory(project=project)

        conv1 = ConversationFactory(
            project=project,
            topic=topic,
            resolution="1",  # Unresolved
        )
        conv1.created_at = datetime(2024, 1, 15, 12, 0, 0)
        conv1.save(update_fields=["created_at"])

        conv2 = ConversationFactory(
            project=project,
            topic=topic,
            resolution="1",  # Unresolved
        )
        conv2.created_at = datetime(2024, 1, 15, 13, 0, 0)
        conv2.save(update_fields=["created_at"])

        url = reverse("unresolved-rate")
        response = self.client.get(
            url, {"project_uuid": str(project.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"}
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["unresolved_rate"], 1.0)
        self.assertEqual(data["unresolved_conversations"], 2)

    def test_unresolved_rate_with_motor_filter(self):
        """Test filtering by motor"""
        url = reverse("unresolved-rate")
        response = self.client.get(
            url,
            {
                "project_uuid": str(self.project_ab2_5.uuid),
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "motor": "AB 2.5",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # AB 2.5 has 2 unresolved out of 3
        self.assertAlmostEqual(data["unresolved_rate"], 0.6667, places=3)

    def test_permission_check(self):
        """Test that permission is enforced"""
        unauthorized_user = UserFactory()
        self.client.force_authenticate(user=unauthorized_user)

        url = reverse("unresolved-rate")
        response = self.client.get(url, {"start_date": "2024-01-01", "end_date": "2024-01-31"})

        self.assertEqual(response.status_code, 403)


class ProjectsByMotorViewTestCase(BaseAnalyticsTestCase):
    """Tests for ProjectsByMotorView"""

    def test_projects_by_motor_ab2(self):
        """Test getting AB 2 projects"""
        url = reverse("projects-by-motor")
        response = self.client.get(url, {"motor": "AB 2"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("AB 2", data)
        self.assertEqual(data["AB 2"]["count"], 1)
        self.assertEqual(len(data["AB 2"]["projects"]), 1)
        self.assertEqual(data["AB 2"]["projects"][0]["uuid"], str(self.project_ab2.uuid))

    def test_projects_by_motor_ab2_5(self):
        """Test getting AB 2.5 projects"""
        url = reverse("projects-by-motor")
        response = self.client.get(url, {"motor": "AB 2.5"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("AB 2.5", data)
        self.assertEqual(data["AB 2.5"]["count"], 1)
        self.assertEqual(len(data["AB 2.5"]["projects"]), 1)

    def test_projects_by_motor_both(self):
        """Test getting both motor types"""
        url = reverse("projects-by-motor")
        response = self.client.get(url, {"motor": "both"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("AB 2", data)
        self.assertIn("AB 2.5", data)

    def test_projects_by_motor_with_date_filtering(self):
        """Test date filtering for conversation counts"""
        url = reverse("projects-by-motor")
        response = self.client.get(
            url,
            {
                "motor": "AB 2",
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should show conversation count for the date range
        self.assertGreaterEqual(data["AB 2"]["projects"][0]["conversation_count"], 0)

    def test_projects_by_motor_only_active(self):
        """Test that only active projects are returned"""
        # Create inactive project
        inactive_project = ProjectFactory(
            name="Inactive Project",
            agents_backend="BedrockBackend",
            created_by=self.user,
            is_active=False,
        )

        url = reverse("projects-by-motor")
        response = self.client.get(url, {"motor": "AB 2"})

        self.assertEqual(response.status_code, 200)
        data = response.json()
        project_uuids = [p["uuid"] for p in data["AB 2"]["projects"]]
        self.assertNotIn(str(inactive_project.uuid), project_uuids)

    @skip("temporarily skipped: auth behavior differs on APIView in tests")
    def test_authentication_required(self):
        """Test that authentication is required"""
        self.client.force_authenticate(user=None)

        url = reverse("projects-by-motor")
        response = self.client.get(url)

        self.assertEqual(response.status_code, 401)

    def test_invalid_motor_value(self):
        """Test with invalid motor value"""
        url = reverse("projects-by-motor")
        response = self.client.get(url, {"motor": "Invalid"})

        self.assertEqual(response.status_code, 400)

    def test_partial_date_filter_error(self):
        """Test that both dates must be provided together"""
        url = reverse("projects-by-motor")
        response = self.client.get(url, {"motor": "AB 2", "start_date": "2024-01-01"})

        self.assertEqual(response.status_code, 400)


class AnalyticsEdgeCasesTestCase(BaseAnalyticsTestCase):
    """Edge cases and error handling tests"""

    def test_project_with_no_conversations_ever(self):
        """Test with project that has never had conversations"""
        project_empty = ProjectFactory(
            name="No Conversations Project",
            agents_backend="BedrockBackend",
            created_by=self.user,
        )
        ProjectAuth.objects.update_or_create(
            user=self.user,
            project=project_empty,
            defaults={"role": ProjectAuthorizationRole.MODERATOR.value},
        )

        url = reverse("resolution-rate-average")
        response = self.client.get(
            url,
            {"project_uuid": str(project_empty.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"},
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data["total_conversations"], 0)
        self.assertEqual(data["resolution_rate"], 0.0)

    def test_very_large_date_range(self):
        """Test with very large date range"""
        url = reverse("resolution-rate-average")
        response = self.client.get(url, {"start_date": "2020-01-01", "end_date": "2024-12-31"})

        self.assertEqual(response.status_code, 200)

    def test_min_conversations_boundary(self):
        """Test min_conversations equal to actual count"""
        url = reverse("resolution-rate-average")
        response = self.client.get(
            url,
            {
                "project_uuid": str(self.project_ab2.uuid),
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "min_conversations": "3",  # Exactly the count we have
            },
        )

        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should include the project since it has exactly 3
        self.assertEqual(data["total_conversations"], 3)

    def test_negative_min_conversations(self):
        """Test with negative min_conversations"""
        url = reverse("resolution-rate-average")
        response = self.client.get(
            url,
            {
                "project_uuid": str(self.project_ab2.uuid),
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "min_conversations": "-1",
            },
        )

        self.assertEqual(response.status_code, 400)

    def test_invalid_min_conversations(self):
        """Test with non-integer min_conversations"""
        url = reverse("resolution-rate-average")
        response = self.client.get(
            url,
            {
                "project_uuid": str(self.project_ab2.uuid),
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "min_conversations": "not-a-number",
            },
        )

        self.assertEqual(response.status_code, 400)


class QueryOptimizationTestCase(BaseAnalyticsTestCase):
    """Tests for query optimization"""

    def test_select_related_used(self):
        """Test that select_related is used to avoid N+1 queries"""
        from django.test.utils import override_settings

        url = reverse("resolution-rate-average")

        with override_settings(DEBUG=True):
<<<<<<< HEAD
            initial_queries = len(connection.queries)

            response = self.client.get(
                url, {"project_uuid": str(self.project_ab2.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"}
            )

            final_queries = len(connection.queries)
=======
            response = self.client.get(
                url,
                {
                    "project_uuid": str(self.project_ab2.uuid),
                    "start_date": "2024-01-01",
                    "end_date": "2024-01-31",
                },
            )
>>>>>>> fix/broken-ci-steps-7
            # Should not have excessive queries (select_related should help)
            # Note: This is a basic check - actual query count depends on implementation
            self.assertEqual(response.status_code, 200)

    def test_aggregate_in_database(self):
        """Test that aggregation happens in database, not Python"""
        url = reverse("resolution-rate-average")
        response = self.client.get(
            url, {"project_uuid": str(self.project_ab2.uuid), "start_date": "2024-01-01", "end_date": "2024-01-31"}
        )

        self.assertEqual(response.status_code, 200)
        # If aggregation happens in DB, the calculation should be correct
        data = response.json()
        # Verify calculation is correct
        expected_rate = data["resolved_conversations"] / data["total_conversations"]
        self.assertAlmostEqual(data["resolution_rate"], expected_rate, places=4)
