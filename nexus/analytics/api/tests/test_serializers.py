from django.test import TestCase
from rest_framework import serializers

from nexus.analytics.api.serializers import (
    ResolutionRateSerializer,
    IndividualResolutionRateSerializer,
    IndividualProjectResolutionSerializer,
    UnresolvedRateSerializer,
    ProjectsByMotorSerializer,
    MotorProjectsSerializer,
    ProjectByMotorSerializer,
)


class AnalyticsSerializersTestCase(TestCase):
    """Tests for analytics serializers"""

    def test_resolution_rate_serializer_valid_data(self):
        """Test ResolutionRateSerializer with valid data"""
        data = {
            "resolution_rate": 0.75,
            "unresolved_rate": 0.25,
            "total_conversations": 100,
            "resolved_conversations": 75,
            "unresolved_conversations": 25,
            "breakdown": {
                "resolved": 75,
                "unresolved": 25,
                "in_progress": 0,
                "unclassified": 0,
                "has_chat_room": 0,
            },
            "filters": {
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
                "motor": "AB 2",
                "min_conversations": 10,
            },
        }

        serializer = ResolutionRateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_resolution_rate_serializer_required_fields(self):
        """Test ResolutionRateSerializer requires all fields"""
        serializer = ResolutionRateSerializer(data={})
        self.assertFalse(serializer.is_valid())
        # Check that required fields are validated
        self.assertIn("resolution_rate", serializer.errors)
        self.assertIn("total_conversations", serializer.errors)

    def test_resolution_rate_serializer_float_validation(self):
        """Test ResolutionRateSerializer float field validation"""
        data = {
            "resolution_rate": "not-a-float",
            "unresolved_rate": 0.25,
            "total_conversations": 100,
            "resolved_conversations": 75,
            "unresolved_conversations": 25,
            "breakdown": {},
            "filters": {},
        }

        serializer = ResolutionRateSerializer(data=data)
        self.assertFalse(serializer.is_valid())
        self.assertIn("resolution_rate", serializer.errors)

    def test_resolution_rate_serializer_empty_breakdown(self):
        """Test ResolutionRateSerializer with empty breakdown"""
        data = {
            "resolution_rate": 0.0,
            "unresolved_rate": 0.0,
            "total_conversations": 0,
            "resolved_conversations": 0,
            "unresolved_conversations": 0,
            "breakdown": {},
            "filters": {},
        }

        serializer = ResolutionRateSerializer(data=data)
        self.assertTrue(serializer.is_valid())

    def test_individual_project_resolution_serializer(self):
        """Test IndividualProjectResolutionSerializer"""
        data = {
            "project_uuid": "123e4567-e89b-12d3-a456-426614174000",
            "project_name": "Test Project",
            "motor": "AB 2",
            "resolution_rate": 0.75,
            "total": 100,
            "resolved": 75,
            "unresolved": 25,
        }

        serializer = IndividualProjectResolutionSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_individual_resolution_rate_serializer(self):
        """Test IndividualResolutionRateSerializer"""
        data = {
            "projects": [
                {
                    "project_uuid": "123e4567-e89b-12d3-a456-426614174000",
                    "project_name": "Project 1",
                    "motor": "AB 2",
                    "resolution_rate": 0.75,
                    "total": 100,
                    "resolved": 75,
                    "unresolved": 25,
                }
            ],
            "filters": {
                "start_date": "2024-01-01",
                "end_date": "2024-01-31",
            },
        }

        serializer = IndividualResolutionRateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_individual_resolution_rate_serializer_list(self):
        """Test IndividualResolutionRateSerializer with multiple projects"""
        data = {
            "projects": [
                {
                    "project_uuid": "123e4567-e89b-12d3-a456-426614174000",
                    "project_name": "Project 1",
                    "motor": "AB 2",
                    "resolution_rate": 0.75,
                    "total": 100,
                    "resolved": 75,
                    "unresolved": 25,
                },
                {
                    "project_uuid": "223e4567-e89b-12d3-a456-426614174001",
                    "project_name": "Project 2",
                    "motor": "AB 2.5",
                    "resolution_rate": 0.50,
                    "total": 50,
                    "resolved": 25,
                    "unresolved": 25,
                },
            ],
            "filters": {},
        }

        serializer = IndividualResolutionRateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_unresolved_rate_serializer(self):
        """Test UnresolvedRateSerializer"""
        data = {
            "unresolved_rate": 0.25,
            "total_conversations": 100,
            "unresolved_conversations": 25,
            "filters": {},
        }

        serializer = UnresolvedRateSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_project_by_motor_serializer(self):
        """Test ProjectByMotorSerializer"""
        data = {
            "uuid": "123e4567-e89b-12d3-a456-426614174000",
            "name": "Test Project",
            "conversation_count": 100,
        }

        serializer = ProjectByMotorSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_motor_projects_serializer(self):
        """Test MotorProjectsSerializer"""
        data = {
            "count": 2,
            "projects": [
                {
                    "uuid": "123e4567-e89b-12d3-a456-426614174000",
                    "name": "Project 1",
                    "conversation_count": 100,
                },
                {
                    "uuid": "223e4567-e89b-12d3-a456-426614174001",
                    "name": "Project 2",
                    "conversation_count": 50,
                },
            ],
        }

        serializer = MotorProjectsSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_projects_by_motor_serializer(self):
        """Test ProjectsByMotorSerializer"""
        data = {
            "AB 2": {
                "count": 1,
                "projects": [
                    {
                        "uuid": "123e4567-e89b-12d3-a456-426614174000",
                        "name": "AB2 Project",
                        "conversation_count": 100,
                    }
                ],
            },
            "AB 2.5": {
                "count": 1,
                "projects": [
                    {
                        "uuid": "223e4567-e89b-12d3-a456-426614174001",
                        "name": "AB2.5 Project",
                        "conversation_count": 50,
                    }
                ],
            },
        }

        serializer = ProjectsByMotorSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_projects_by_motor_serializer_single_motor(self):
        """Test ProjectsByMotorSerializer with only one motor"""
        data = {
            "AB 2": {
                "count": 1,
                "projects": [
                    {
                        "uuid": "123e4567-e89b-12d3-a456-426614174000",
                        "name": "AB2 Project",
                        "conversation_count": 100,
                    }
                ],
            }
        }

        serializer = ProjectsByMotorSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

    def test_projects_by_motor_serializer_to_representation(self):
        """Test custom to_representation method"""
        data = {
            "AB 2": {
                "count": 1,
                "projects": [],
            }
        }

        serializer = ProjectsByMotorSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        representation = serializer.to_representation(data)
        self.assertIn("AB 2", representation)
        self.assertNotIn("AB_2", representation)  # Should use space, not underscore

