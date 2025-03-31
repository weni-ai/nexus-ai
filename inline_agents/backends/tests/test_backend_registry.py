from unittest import TestCase

from inline_agents.backend import InlineAgentsBackend
from inline_agents.backends import BackendsRegistry
from inline_agents.backends.exceptions import (
    BackendAlreadyRegistered,
    UnregisteredBackend,
)


class MockBackend(InlineAgentsBackend):
    def invoke_agents(self, team):
        pass


class AnotherMockBackend(InlineAgentsBackend):
    def invoke_agents(self, team):
        pass


class TestBackendRegistry(TestCase):
    def setUp(self):
        # Limpa o registro antes de cada teste
        BackendsRegistry._names = []
        BackendsRegistry._options = {}
        BackendsRegistry._default_backend = None

    def test_register_backend(self):
        backend = MockBackend()
        BackendsRegistry.register(backend)
        self.assertIn("MockBackend", BackendsRegistry._names)
        self.assertIn("MockBackend", BackendsRegistry._options)

    def test_register_backend_already_registered(self):
        backend = MockBackend()
        BackendsRegistry.register(backend)
        with self.assertRaises(BackendAlreadyRegistered):
            BackendsRegistry.register(backend)

    def test_get_registered_backend(self):
        backend = MockBackend()
        BackendsRegistry.register(backend)
        retrieved_backend = BackendsRegistry.get_backend("MockBackend")
        self.assertEqual(retrieved_backend, backend)

    def test_get_unregistered_backend(self):
        with self.assertRaises(UnregisteredBackend):
            BackendsRegistry.get_backend("NonExistentBackend")

    def test_register_multiple_backends(self):
        backend1 = MockBackend()
        backend2 = AnotherMockBackend()
        BackendsRegistry.register(backend1)
        BackendsRegistry.register(backend2)
        self.assertIn("MockBackend", BackendsRegistry._names)
        self.assertIn("AnotherMockBackend", BackendsRegistry._names)
        self.assertIn("MockBackend", BackendsRegistry._options)
        self.assertIn("AnotherMockBackend", BackendsRegistry._options)

    def test_set_and_get_default_backend(self):
        backend = MockBackend()
        BackendsRegistry.register(backend, set_default=True)
        default_backend = BackendsRegistry.get_default_backend()
        self.assertEqual(default_backend, backend)

    def test_get_default_backend_not_set(self):
        with self.assertRaises(UnregisteredBackend):
            BackendsRegistry.get_default_backend()
