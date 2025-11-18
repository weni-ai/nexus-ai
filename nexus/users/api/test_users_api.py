from rest_framework import status
from rest_framework.test import APIClient, APITestCase

from nexus.users.models import User


class UserDetailsViewTestCase(APITestCase):
    def setUp(self):
        self.client = APIClient()

        self.test_user = User.objects.create_user(email="test@example.com", language="pt-br", is_active=True)
        self.other_user = User.objects.create_user(email="other@example.com", language="en", is_active=False)

    def test_get_user_details_requires_authentication(self):
        response = self.client.get("/api/users/details/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_get_user_details_authenticated(self):
        self.client.force_authenticate(user=self.test_user)
        response = self.client.get("/api/users/details/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "test@example.com")
        self.assertEqual(response.data["language"], "pt-br")
        self.assertTrue(response.data["is_active"])

    def test_user_details_serialization(self):
        self.client.force_authenticate(user=self.test_user)
        response = self.client.get("/api/users/details/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertIn("email", response.data)
        self.assertIn("language", response.data)
        self.assertIn("is_active", response.data)

    def test_user_details_returns_only_authenticated_user(self):
        self.client.force_authenticate(user=self.test_user)
        response = self.client.get("/api/users/details/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertNotEqual(response.data["email"], "other@example.com")
        self.assertEqual(response.data["email"], "test@example.com")

    def test_different_user_gets_their_own_data(self):
        self.client.force_authenticate(user=self.test_user)
        response1 = self.client.get("/api/users/details/")

        # User 1
        self.assertEqual(response1.status_code, status.HTTP_200_OK)
        self.assertEqual(response1.data["email"], "test@example.com")
        self.assertEqual(response1.data["language"], "pt-br")
        self.assertTrue(response1.data["is_active"])

        # User 2
        self.client.force_authenticate(user=self.other_user)
        response2 = self.client.get("/api/users/details/")

        self.assertEqual(response2.status_code, status.HTTP_200_OK)
        self.assertEqual(response2.data["email"], "other@example.com")
        self.assertEqual(response2.data["language"], "en")
        self.assertFalse(response2.data["is_active"])

    def test_retrieve_method_works(self):
        self.client.force_authenticate(user=self.test_user)
        response = self.client.get("/api/users/details/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIsInstance(response.data, dict)

    def test_response_data_structure(self):
        self.client.force_authenticate(user=self.test_user)
        response = self.client.get("/api/users/details/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)

        self.assertIsInstance(response.data, dict)

        expected_fields = {"email", "language", "is_active"}
        actual_fields = set(response.data.keys())
        self.assertEqual(actual_fields, expected_fields)
