"""
Example test file showing how to use MockCacheService and MockCacheRepository.

This file demonstrates testing patterns for CacheService.
Copy and adapt these patterns for your actual tests.
"""

import time

from django.test import SimpleTestCase

from router.repositories.mocks import MockCacheRepository
from router.tests.mocks import MockCacheService


class CacheServiceTestCase(SimpleTestCase):
    """Example test case using MockCacheService."""

    def setUp(self):
        """Set up test fixtures."""
        self.cache_service = MockCacheService()

    def tearDown(self):
        """Clean up after tests."""
        self.cache_service.clear_all()

    def test_get_project_data_caches_on_miss(self):
        """Test that project data is cached on first access."""
        project_uuid = "test-project-uuid"
        expected_data = {"uuid": project_uuid, "name": "Test Project", "agents_backend": "OpenAIBackend"}

        # First call - cache miss, should fetch and cache
        result = self.cache_service.get_project_data(project_uuid, lambda uuid: expected_data.copy())

        self.assertEqual(result, expected_data)
        self.assertEqual(self.cache_service.get_cache_size(), 1)
        self.assertIn(f"project:{project_uuid}:data", self.cache_service.get_cache_keys())

    def test_get_project_data_returns_cached_data(self):
        """Test that cached project data is returned on second access."""
        project_uuid = "test-project-uuid"
        expected_data = {"uuid": project_uuid, "name": "Test Project"}

        # First call - cache miss
        self.cache_service.get_project_data(project_uuid, lambda uuid: expected_data.copy())

        # Second call - cache hit, fetch_func should not be called
        call_count = {"count": 0}

        def fetch_func(uuid):
            call_count["count"] += 1
            return expected_data.copy()

        result = self.cache_service.get_project_data(project_uuid, fetch_func)

        self.assertEqual(result, expected_data)
        self.assertEqual(call_count["count"], 0)  # fetch_func should not be called

    def test_get_all_project_data_caches_composite_and_individual(self):
        """Test that get_all_project_data caches both composite and individual keys."""
        project_uuid = "test-project-uuid"
        agents_backend = "OpenAIBackend"

        project_data = {"uuid": project_uuid, "agents_backend": agents_backend}
        content_base_data = {"uuid": "content-base-uuid", "title": "Test Content Base"}
        team_data = [{"agentName": "Agent1", "instruction": "Test instruction"}]
        guardrails_data = {"guardrailIdentifier": "test-guardrail"}

        fetch_funcs = {
            "project": lambda uuid: project_data.copy(),
            "content_base": lambda uuid: content_base_data.copy(),
            "team": lambda uuid, backend: team_data.copy(),
            "guardrails": lambda uuid: guardrails_data.copy(),
        }

        # Get all data
        result = self.cache_service.get_all_project_data(project_uuid, agents_backend, fetch_funcs)

        # Verify composite key exists
        self.assertIn(f"project:{project_uuid}:all", self.cache_service.get_cache_keys())

        # Verify individual keys exist
        self.assertIn(f"project:{project_uuid}:data", self.cache_service.get_cache_keys())
        self.assertIn(f"project:{project_uuid}:content_base", self.cache_service.get_cache_keys())
        self.assertIn(f"project:{project_uuid}:team:{agents_backend}", self.cache_service.get_cache_keys())
        self.assertIn(f"project:{project_uuid}:guardrails", self.cache_service.get_cache_keys())

        # Verify data
        self.assertEqual(result["project"], project_data)
        self.assertEqual(result["content_base"], content_base_data)
        self.assertEqual(result["team"], team_data)
        self.assertEqual(result["guardrails"], guardrails_data)

    def test_invalidate_project_cache_clears_all_keys(self):
        """Test that invalidate_project_cache clears both composite and individual keys."""
        project_uuid = "test-project-uuid"
        agents_backend = "OpenAIBackend"

        # Cache some data
        self.cache_service.get_project_data(project_uuid, lambda uuid: {"uuid": project_uuid})
        self.cache_service.get_all_project_data(
            project_uuid,
            agents_backend,
            {
                "project": lambda uuid: {"uuid": project_uuid},
                "content_base": lambda uuid: {"uuid": "content-base"},
                "team": lambda uuid, backend: [],
                "guardrails": lambda uuid: {},
            },
        )

        # Verify keys exist
        self.assertGreater(self.cache_service.get_cache_size(), 0)

        # Invalidate
        self.cache_service.invalidate_project_cache(project_uuid)

        # Verify all keys are cleared
        keys = self.cache_service.get_cache_keys()
        project_keys = [key for key in keys if key.startswith(f"project:{project_uuid}")]
        self.assertEqual(len(project_keys), 0)

    def test_invalidate_team_cache_clears_composite_and_team_keys(self):
        """Test that invalidate_team_cache clears composite and team keys."""
        project_uuid = "test-project-uuid"
        agents_backend = "OpenAIBackend"

        # Cache data
        self.cache_service.get_all_project_data(
            project_uuid,
            agents_backend,
            {
                "project": lambda uuid: {"uuid": project_uuid, "agents_backend": agents_backend},
                "content_base": lambda uuid: {"uuid": "content-base"},
                "team": lambda uuid, backend: [{"agentName": "Agent1"}],
                "guardrails": lambda uuid: {},
            },
        )

        # Verify composite key exists
        self.assertIn(f"project:{project_uuid}:all", self.cache_service.get_cache_keys())
        self.assertIn(f"project:{project_uuid}:team:{agents_backend}", self.cache_service.get_cache_keys())

        # Invalidate team cache
        self.cache_service.invalidate_team_cache(project_uuid, agents_backend)

        # Verify composite and team keys are cleared
        self.assertNotIn(f"project:{project_uuid}:all", self.cache_service.get_cache_keys())
        self.assertNotIn(f"project:{project_uuid}:team:{agents_backend}", self.cache_service.get_cache_keys())

        # But other keys should still exist (if they were cached individually)
        # Note: In real scenario, you might want to re-cache after invalidation

    def test_workflow_cache_methods(self):
        """Test workflow-level cache methods."""
        workflow_id = "test-workflow-id"
        data = {"test": "data"}

        # Cache workflow data
        self.cache_service.cache_workflow_data(workflow_id, "test_data", data)

        # Get workflow data
        result = self.cache_service.get_workflow_data(workflow_id, "test_data")
        self.assertEqual(result, data)

        # Clear workflow cache
        self.cache_service.clear_workflow_cache(workflow_id)
        result = self.cache_service.get_workflow_data(workflow_id, "test_data")
        self.assertIsNone(result)


class CacheRepositoryTestCase(SimpleTestCase):
    """Example test case using MockCacheRepository directly."""

    def setUp(self):
        """Set up test fixtures."""
        self.repository = MockCacheRepository()

    def tearDown(self):
        """Clean up after tests."""
        self.repository.clear()

    def test_get_set_delete(self):
        """Test basic get/set/delete operations."""
        key = "test:key"
        value = {"test": "data"}

        # Set
        self.repository.set(key, value, ttl=3600)

        # Get
        result = self.repository.get(key)
        self.assertEqual(result, value)

        # Delete
        self.repository.delete(key)
        result = self.repository.get(key)
        self.assertIsNone(result)

    def test_delete_pattern(self):
        """Test pattern-based deletion."""
        # Set multiple keys
        self.repository.set("project:uuid1:data", {"data": 1}, ttl=3600)
        self.repository.set("project:uuid1:content_base", {"data": 2}, ttl=3600)
        self.repository.set("project:uuid2:data", {"data": 3}, ttl=3600)

        # Delete pattern
        self.repository.delete_pattern("project:uuid1:*")

        # Verify uuid1 keys are deleted
        self.assertIsNone(self.repository.get("project:uuid1:data"))
        self.assertIsNone(self.repository.get("project:uuid1:content_base"))

        # Verify uuid2 key still exists
        self.assertIsNotNone(self.repository.get("project:uuid2:data"))

    def test_ttl_expiration(self):
        """Test that TTL expiration works."""
        key = "test:key"
        value = {"test": "data"}

        # Set with short TTL
        self.repository.set(key, value, ttl=1)

        # Should exist immediately
        self.assertTrue(self.repository.exists(key))

        # Wait for expiration
        time.sleep(1.1)

        # Should be expired
        self.assertFalse(self.repository.exists(key))
        self.assertIsNone(self.repository.get(key))
