"""Tests for simulation Redis manager pipeline version override (preview default channel)."""

from unittest.mock import patch

from django.test import SimpleTestCase

from nexus.projects.simulation_model_cache import simulation_manager_pipeline_version_redis_key
from router.tasks.invoke import apply_simulation_manager_pipeline_version_override


class SimulationManagerPipelineVersionKeyTest(SimpleTestCase):
    def test_different_contact_urns_yield_different_redis_keys_same_project(self):
        pid = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
        k1 = simulation_manager_pipeline_version_redis_key(pid, "ext:urn-a")
        k2 = simulation_manager_pipeline_version_redis_key(pid, "ext:urn-b")
        self.assertNotEqual(k1, k2)
        self.assertTrue(k1.startswith("simulation_manager_pipeline_version:"))
        self.assertTrue(k2.startswith("simulation_manager_pipeline_version:"))


class ApplySimulationManagerPipelineVersionOverrideTest(SimpleTestCase):
    def test_production_channel_ignores_redis(self):
        with patch("router.tasks.invoke._get_simulation_manager_pipeline_version", return_value="2.7") as m:
            out = apply_simulation_manager_pipeline_version_override(
                False,
                "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "ext:foo",
                "2.6",
            )
        self.assertEqual(out, "2.6")
        m.assert_not_called()

    def test_preview_channel_uses_redis_when_set(self):
        with patch("router.tasks.invoke._get_simulation_manager_pipeline_version", return_value=" 2.7 \n") as m:
            out = apply_simulation_manager_pipeline_version_override(
                True,
                "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "ext:foo",
                "2.6",
            )
        self.assertEqual(out, "2.7")
        m.assert_called_once()

    def test_preview_channel_whitespace_cache_falls_back_to_base(self):
        with patch("router.tasks.invoke._get_simulation_manager_pipeline_version", return_value="   ") as m:
            out = apply_simulation_manager_pipeline_version_override(
                True,
                "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "ext:foo",
                "2.6",
            )
        self.assertEqual(out, "2.6")
        m.assert_called_once()

    def test_preview_no_redis_uses_base(self):
        with patch("router.tasks.invoke._get_simulation_manager_pipeline_version", return_value=None):
            out = apply_simulation_manager_pipeline_version_override(
                True,
                "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
                "ext:foo",
                "2.6",
            )
        self.assertEqual(out, "2.6")
