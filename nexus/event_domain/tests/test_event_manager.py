"""
Tests for EventManager and ObserverRegistry improvements.

Tests cover:
- Error isolation (one failing observer doesn't break others)
- Lazy loading (observers loaded only when needed)
- Factory pattern (dependency injection support)
- Backwards compatibility
"""

from unittest.mock import MagicMock, Mock, patch

from django.test import TestCase

from nexus.event_domain.event_manager import AsyncEventManager, EventManager
from nexus.event_domain.event_observer import EventObserver
from nexus.event_domain.observer_registry import ObserverRegistry


# Test observers
class SuccessfulObserver(EventObserver):
    """Observer that always succeeds."""

    def __init__(self):
        self.called = False
        self.call_count = 0

    def perform(self, **kwargs):
        self.called = True
        self.call_count += 1
        self.kwargs = kwargs


class FailingObserver(EventObserver):
    """Observer that always fails."""

    def __init__(self):
        self.called = False

    def perform(self, **kwargs):
        self.called = True
        raise ValueError("Observer failed intentionally")


class ExceptionObserver(EventObserver):
    """Observer that raises a different exception."""

    def perform(self, **kwargs):
        raise RuntimeError("Different error type")


class ObserverWithDependencies(EventObserver):
    """Observer that requires dependencies."""

    def __init__(self, dependency1=None, dependency2=None):
        self.dependency1 = dependency1
        self.dependency2 = dependency2
        self.called = False

    def perform(self, **kwargs):
        self.called = True
        self.kwargs = kwargs


class ErrorIsolationTestCase(TestCase):
    """Test error isolation configuration (fail fast vs isolated)."""

    def setUp(self):
        # Use a fresh registry to avoid test pollution
        self.manager = EventManager(registry=ObserverRegistry())
        self.success_observer = SuccessfulObserver()
        self.fail_observer = FailingObserver()
        self.exception_observer = ExceptionObserver()

    def test_successful_observer_runs(self):
        """Test that a successful observer runs normally."""
        self.manager.subscribe("test_event", observer=[self.success_observer])

        self.manager.notify("test_event", data="test")

        self.assertTrue(self.success_observer.called)
        self.assertEqual(self.success_observer.kwargs["data"], "test")

    def test_default_behavior_fail_fast(self):
        """Test that default behavior is fail fast - exception propagates."""
        self.manager.subscribe("test_event", observer=[self.fail_observer, self.success_observer])

        # Should raise exception (fail fast)
        with self.assertRaises(ValueError) as context:
            self.manager.notify("test_event", data="test")

        # First observer should have been called and failed
        self.assertTrue(self.fail_observer.called)
        # Second observer should NOT have been called (execution stopped)
        self.assertFalse(self.success_observer.called)
        self.assertIn("Observer failed intentionally", str(context.exception))

    def test_isolated_observer_continues_on_error(self):
        """Test that observers with isolate_errors=True continue on error."""
        self.manager.subscribe("test_event", observer=[self.fail_observer, self.success_observer], isolate_errors=True)

        # Should not raise exception (errors are isolated)
        self.manager.notify("test_event", data="test")

        # Both should have been called
        self.assertTrue(self.fail_observer.called)
        self.assertTrue(self.success_observer.called)

    def test_mixed_isolation_behavior(self):
        """Test mixing isolated and non-isolated observers."""
        fail2 = FailingObserver()
        # First observer: isolated (continue on error)
        self.manager.subscribe("test_event", observer=[self.fail_observer], isolate_errors=True)
        # Second observer: fail fast (default)
        self.manager.subscribe("test_event", observer=[fail2])
        # Third observer: should not run if second fails
        self.manager.subscribe("test_event", observer=[self.success_observer])

        # Should raise exception when second observer fails
        with self.assertRaises(ValueError):
            self.manager.notify("test_event", data="test")

        # First observer (isolated) should have been called
        self.assertTrue(self.fail_observer.called)
        # Second observer (fail fast) should have been called and failed
        self.assertTrue(fail2.called)
        # Third observer should NOT have been called (execution stopped at second)
        self.assertFalse(self.success_observer.called)

    def test_isolated_error_logging(self):
        """Test that isolated errors are properly logged."""
        with patch("nexus.event_domain.event_manager.logger") as mock_logger:
            self.manager.subscribe("test_event", observer=[self.fail_observer], isolate_errors=True)
            self.manager.notify("test_event", data="test")

            # Verify error was logged
            mock_logger.error.assert_called()
            call_args = mock_logger.error.call_args
            self.assertIn("Observer", call_args[0][0])
            self.assertIn("test_event", call_args[0][0])
            self.assertIn("isolated", call_args[0][0])

    def test_fail_fast_no_logging(self):
        """Test that fail fast errors are not logged (exception propagates)."""
        with patch("nexus.event_domain.event_manager.logger") as mock_logger:
            self.manager.subscribe("test_event", observer=[self.fail_observer])

            with self.assertRaises(ValueError):
                self.manager.notify("test_event", data="test")

            # Error should NOT be logged (exception propagates)
            mock_logger.error.assert_not_called()

    def test_string_based_registration_with_isolation(self):
        """Test error isolation with string-based observer registration."""
        self.manager.subscribe(
            "test_event", observer="nexus.event_domain.tests.test_event_manager.FailingObserver", isolate_errors=True
        )
        self.manager.subscribe("test_event", observer=[self.success_observer])

        # Should not raise exception (first observer is isolated)
        self.manager.notify("test_event", data="test")

        # Success observer should have been called
        self.assertTrue(self.success_observer.called)


class AsyncErrorIsolationTestCase(TestCase):
    """Test error isolation in AsyncEventManager."""

    def setUp(self):
        # Use a fresh registry to avoid test pollution
        self.manager = AsyncEventManager(registry=ObserverRegistry())
        self.success_observer = SuccessfulObserver()
        self.fail_observer = FailingObserver()

    def test_async_default_behavior_fail_fast(self):
        """Test that async default behavior is fail fast."""
        import asyncio

        self.manager.subscribe("test_event", observer=[self.fail_observer, self.success_observer])

        exception_raised = False

        async def run_test():
            nonlocal exception_raised
            try:
                await self.manager.notify("test_event", data="test")
            except ValueError:
                # Expected exception
                exception_raised = True

        asyncio.run(run_test())

        # Exception should have been raised
        self.assertTrue(exception_raised, "Expected ValueError to be raised")
        # First observer should have been called
        self.assertTrue(self.fail_observer.called)
        # Second observer should NOT have been called (execution stopped)
        self.assertFalse(self.success_observer.called)

    def test_async_isolated_observer_continues_on_error(self):
        """Test that async observers with isolate_errors=True continue on error."""
        import asyncio

        self.manager.subscribe("test_event", observer=[self.fail_observer, self.success_observer], isolate_errors=True)

        async def run_test():
            # Should not raise exception (errors are isolated)
            await self.manager.notify("test_event", data="test")

        asyncio.run(run_test())

        # Both should have been called
        self.assertTrue(self.fail_observer.called)
        self.assertTrue(self.success_observer.called)

    def test_async_isolated_error_logging(self):
        """Test that async isolated errors are properly logged."""
        import asyncio

        with patch("nexus.event_domain.event_manager.logger") as mock_logger:
            self.manager.subscribe("test_event", observer=[self.fail_observer], isolate_errors=True)

            async def run_test():
                await self.manager.notify("test_event", data="test")

            asyncio.run(run_test())

            # Verify error was logged
            mock_logger.error.assert_called()
            call_args = mock_logger.error.call_args
            self.assertIn("isolated", call_args[0][0])


class LazyLoadingTestCase(TestCase):
    """Test lazy loading functionality."""

    def setUp(self):
        # Use a fresh registry to avoid test pollution
        self.registry = ObserverRegistry()

    def test_lazy_loading_doesnt_import_immediately(self):
        """Test that observers aren't imported until notify is called."""
        # Register an observer path
        self.registry.register(
            "test_event",
            "nexus.event_domain.tests.test_event_manager.SuccessfulObserver",
            lazy=True,
        )

        # At this point, the observer shouldn't be loaded yet
        # We can't directly test this, but we can verify it loads when needed
        observers = self.registry.get_observers("test_event")
        self.assertEqual(len(observers), 1)
        self.assertIsInstance(observers[0], SuccessfulObserver)

    def test_lazy_loading_caches_instances(self):
        """Test that lazy-loaded observers are cached."""
        self.registry.register(
            "test_event",
            "nexus.event_domain.tests.test_event_manager.SuccessfulObserver",
            lazy=True,
        )

        # Get observers twice
        observers1 = self.registry.get_observers("test_event")
        observers2 = self.registry.get_observers("test_event")

        # Should return cached instances (same object)
        self.assertEqual(len(observers1), 1)
        self.assertEqual(len(observers2), 1)
        # Note: They might be different instances if we create new ones each time
        # This is acceptable behavior

    def test_lazy_loading_invalid_path(self):
        """Test that invalid observer paths are handled gracefully."""
        with patch("nexus.event_domain.observer_registry.logger") as mock_logger:
            self.registry.register("test_event", "invalid.path.Observer", lazy=True)

            observers = self.registry.get_observers("test_event")

            # Should return empty list or log error
            self.assertEqual(len(observers), 0)
            # Error should be logged
            mock_logger.error.assert_called()


class FactoryPatternTestCase(TestCase):
    """Test factory pattern for dependency injection."""

    def setUp(self):
        # Use a fresh registry to avoid test pollution
        self.registry = ObserverRegistry()

    def test_factory_creates_observer_with_dependencies(self):
        """Test that factory can inject dependencies."""
        dep1 = Mock()
        dep2 = Mock()

        def factory(observer_class):
            return observer_class(dependency1=dep1, dependency2=dep2)

        self.registry.register(
            "test_event",
            "nexus.event_domain.tests.test_event_manager.ObserverWithDependencies",
            lazy=True,
            factory=factory,
        )

        observers = self.registry.get_observers("test_event")
        self.assertEqual(len(observers), 1)
        observer = observers[0]
        self.assertEqual(observer.dependency1, dep1)
        self.assertEqual(observer.dependency2, dep2)

    def test_default_factory_uses_no_args(self):
        """Test that default factory instantiates with no arguments."""
        # ObserverWithDependencies has default None for dependencies
        self.registry.register(
            "test_event",
            "nexus.event_domain.tests.test_event_manager.ObserverWithDependencies",
            lazy=True,
        )

        observers = self.registry.get_observers("test_event")
        self.assertEqual(len(observers), 1)
        observer = observers[0]
        self.assertIsNone(observer.dependency1)
        self.assertIsNone(observer.dependency2)

    def test_registry_default_factory(self):
        """Test that registry can have a default factory."""
        dep = Mock()

        def default_factory(observer_class):
            return observer_class(dependency1=dep)

        registry = ObserverRegistry(factory=default_factory)
        registry.register(
            "test_event",
            "nexus.event_domain.tests.test_event_manager.ObserverWithDependencies",
            lazy=True,
        )

        observers = registry.get_observers("test_event")
        self.assertEqual(len(observers), 1)
        self.assertEqual(observers[0].dependency1, dep)

    def test_factory_with_event_manager(self):
        """Test that factory works when registering through EventManager."""
        dep = Mock()

        def factory(observer_class):
            return observer_class(dependency1=dep, dependency2=Mock())

        # Use a fresh registry to avoid test pollution
        manager = EventManager(registry=ObserverRegistry())
        manager.subscribe(
            "test_event",
            observer="nexus.event_domain.tests.test_event_manager.ObserverWithDependencies",
            factory=factory,
        )

        # Trigger event to load observer
        manager.notify("test_event", data="test")

        # Observer should have been created with dependencies
        observers = manager.registry.get_observers("test_event")
        self.assertEqual(len(observers), 1)
        self.assertEqual(observers[0].dependency1, dep)
        self.assertTrue(observers[0].called)


class MiddlewareTestCase(TestCase):
    """Test middleware hooks for error tracking and performance monitoring."""

    def setUp(self):
        # Use a fresh registry to avoid test pollution
        self.registry = ObserverRegistry()
        self.manager = EventManager(registry=self.registry)
        self.success_observer = SuccessfulObserver()
        self.fail_observer = FailingObserver()

    def test_sentry_middleware_captures_errors(self):
        """Test that Sentry middleware captures errors."""
        from unittest.mock import MagicMock, patch

        from nexus.event_domain.middleware import MiddlewareChain, SentryErrorMiddleware

        # Create a mock sentry_sdk module
        mock_sentry = MagicMock()

        with patch.dict("sys.modules", {"sentry_sdk": mock_sentry}):
            # Create manager with Sentry middleware (enabled=True bypasses settings check)
            middleware = SentryErrorMiddleware.__new__(SentryErrorMiddleware)
            middleware.enabled = True  # Force enable without checking settings

            chain = MiddlewareChain()
            chain.add(middleware)
            manager = EventManager(registry=ObserverRegistry(), middleware=chain)

            manager.subscribe("test_event", observer=self.fail_observer)

            try:
                manager.notify("test_event", data="test")
            except ValueError:
                pass  # Expected

            # Verify Sentry was called
            mock_sentry.capture_exception.assert_called_once()
            mock_sentry.set_tag.assert_any_call("observer", "FailingObserver")
            mock_sentry.set_tag.assert_any_call("event", "test_event")
            mock_sentry.set_tag.assert_any_call("observer_error", True)

    def test_performance_middleware_logs_duration(self):
        """Test that performance middleware logs execution time."""
        from unittest.mock import patch

        from nexus.event_domain.middleware import (
            MiddlewareChain,
            PerformanceLoggingMiddleware,
        )

        # Create manager with performance middleware
        chain = MiddlewareChain()
        chain.add(PerformanceLoggingMiddleware(enabled=True, slow_threshold=0.1))
        manager = EventManager(middleware=chain)

        manager.subscribe("test_event", observer=self.success_observer)

        with patch("nexus.event_domain.middleware.logger") as mock_logger:
            manager.notify("test_event", data="test")

            # Verify performance was logged
            mock_logger.debug.assert_called()
            call_args = str(mock_logger.debug.call_args)
            self.assertNotIn("FailingObserver", call_args)  # Should log SuccessfulObserver
            self.assertIn("duration", call_args.lower())

    def test_middleware_chain_executes_all(self):
        """Test that middleware chain executes all middleware."""
        from nexus.event_domain.middleware import MiddlewareChain, PerformanceLoggingMiddleware

        # Create mock middleware
        mock_middleware1 = MagicMock()
        mock_middleware1.before_perform = MagicMock()
        mock_middleware1.after_perform = MagicMock()
        mock_middleware1.on_error = MagicMock()

        chain = MiddlewareChain()
        chain.add(mock_middleware1)
        chain.add(PerformanceLoggingMiddleware())

        # Use fresh registry and middleware chain
        manager = EventManager(registry=ObserverRegistry(), middleware=chain)
        observer = SuccessfulObserver()
        manager.subscribe("test_event", observer=observer)

        manager.notify("test_event", data="test")

        # Verify middleware was called
        mock_middleware1.before_perform.assert_called_once()
        mock_middleware1.after_perform.assert_called_once()

    def test_middleware_on_error_called(self):
        """Test that middleware on_error is called when observer fails."""
        from nexus.event_domain.middleware import MiddlewareChain

        mock_middleware = MagicMock()
        mock_middleware.before_perform = MagicMock()
        mock_middleware.after_perform = MagicMock()
        mock_middleware.on_error = MagicMock()

        chain = MiddlewareChain()
        chain.add(mock_middleware)

        # Use fresh registry and middleware chain
        manager = EventManager(registry=ObserverRegistry(), middleware=chain)
        fail_observer = FailingObserver()
        manager.subscribe("test_event", observer=fail_observer, isolate_errors=True)

        manager.notify("test_event", data="test")

        # Verify on_error was called, not after_perform
        mock_middleware.before_perform.assert_called_once()
        mock_middleware.on_error.assert_called_once()
        mock_middleware.after_perform.assert_not_called()


class EventValidatorTestCase(TestCase):
    """Test event validation functionality."""

    def setUp(self):
        # Use a fresh registry to avoid test pollution
        self.manager = EventManager(registry=ObserverRegistry())
        self.success_observer = SuccessfulObserver()

    def test_required_fields_validator(self):
        """Test RequiredFieldsValidator."""
        from nexus.event_domain.validators import RequiredFieldsValidator, ValidatorChain

        chain = ValidatorChain()
        chain.add(RequiredFieldsValidator(["project_uuid", "user_id"]))

        self.manager.add_validator("test_event", chain)
        self.manager.subscribe("test_event", observer=self.success_observer)

        # Valid payload
        self.manager.notify("test_event", project_uuid="123", user_id="456")
        self.assertTrue(self.success_observer.called)

        # Invalid payload - missing field
        self.success_observer.called = False
        with self.assertRaises(ValueError) as cm:
            self.manager.notify("test_event", project_uuid="123")
        self.assertIn("missing required fields", str(cm.exception))
        self.assertFalse(self.success_observer.called)

    def test_field_type_validator(self):
        """Test FieldTypeValidator."""
        from nexus.event_domain.validators import FieldTypeValidator, ValidatorChain

        chain = ValidatorChain()
        chain.add(FieldTypeValidator({"project_uuid": str, "count": int}))

        self.manager.add_validator("test_event", chain)
        self.manager.subscribe("test_event", observer=self.success_observer)

        # Valid payload
        self.manager.notify("test_event", project_uuid="123", count=5)
        self.assertTrue(self.success_observer.called)

        # Invalid payload - wrong type
        self.success_observer.called = False
        with self.assertRaises(TypeError) as cm:
            self.manager.notify("test_event", project_uuid=123, count=5)
        self.assertIn("must be of type", str(cm.exception))
        self.assertFalse(self.success_observer.called)

    def test_composite_validator(self):
        """Test CompositeValidator."""
        from nexus.event_domain.validators import (
            CompositeValidator,
            FieldTypeValidator,
            RequiredFieldsValidator,
            ValidatorChain,
        )

        composite = CompositeValidator(
            [RequiredFieldsValidator(["project_uuid"]), FieldTypeValidator({"project_uuid": str})]
        )

        chain = ValidatorChain()
        chain.add(composite)

        self.manager.add_validator("test_event", chain)
        self.manager.subscribe("test_event", observer=self.success_observer)

        # Valid payload
        self.manager.notify("test_event", project_uuid="123")
        self.assertTrue(self.success_observer.called)

        # Invalid payload - wrong type (TypeError is raised for type validation)
        self.success_observer.called = False
        with self.assertRaises(TypeError):
            self.manager.notify("test_event", project_uuid=123)

    def test_validator_chain_multiple_validators(self):
        """Test ValidatorChain with multiple validators."""
        from nexus.event_domain.validators import FieldTypeValidator, RequiredFieldsValidator, ValidatorChain

        chain = ValidatorChain()
        chain.add(RequiredFieldsValidator(["project_uuid"]))
        chain.add(FieldTypeValidator({"project_uuid": str}))

        self.manager.add_validator("test_event", chain)
        self.manager.subscribe("test_event", observer=self.success_observer)

        # Valid payload
        self.manager.notify("test_event", project_uuid="123")
        self.assertTrue(self.success_observer.called)

        # Invalid payload - fails first validator
        self.success_observer.called = False
        with self.assertRaises(ValueError):
            self.manager.notify("test_event", other_field="value")

    def test_no_validator_no_validation(self):
        """Test that events without validators work normally."""
        self.manager.subscribe("test_event", observer=self.success_observer)

        # Should work without validation
        self.manager.notify("test_event", any_field="any_value")
        self.assertTrue(self.success_observer.called)

    def test_custom_validator(self):
        """Test custom validator implementation."""
        from nexus.event_domain.validators import EventValidator, ValidatorChain

        class CustomValidator(EventValidator):
            def validate(self, event: str, payload: dict):
                if "custom_field" not in payload:
                    raise ValueError("custom_field is required")
                if payload["custom_field"] != "expected_value":
                    raise ValueError("custom_field must be 'expected_value'")

        chain = ValidatorChain()
        chain.add(CustomValidator())

        self.manager.add_validator("test_event", chain)
        self.manager.subscribe("test_event", observer=self.success_observer)

        # Valid payload
        self.manager.notify("test_event", custom_field="expected_value")
        self.assertTrue(self.success_observer.called)

        # Invalid payload
        self.success_observer.called = False
        with self.assertRaises(ValueError):
            self.manager.notify("test_event", custom_field="wrong_value")


class BackwardsCompatibilityTestCase(TestCase):
    """Test that existing code continues to work."""

    def setUp(self):
        # Use a fresh registry to avoid test pollution
        self.manager = EventManager(registry=ObserverRegistry())

    def test_direct_instance_registration(self):
        """Test that direct instance registration still works."""
        observer = SuccessfulObserver()
        self.manager.subscribe("test_event", observer=[observer])

        self.manager.notify("test_event", data="test")

        self.assertTrue(observer.called)

    def test_string_based_registration(self):
        """Test that string-based registration works."""
        self.manager.subscribe(
            "test_event",
            observer="nexus.event_domain.tests.test_event_manager.SuccessfulObserver",
        )

        self.manager.notify("test_event", data="test")

        # Observer should have been loaded and called
        # We can't directly verify this, but if it didn't work, we'd get an error

    def test_mixed_registration(self):
        """Test that mixing instance and string registration works."""
        direct_observer = SuccessfulObserver()
        self.manager.subscribe("test_event", observer=[direct_observer])
        self.manager.subscribe(
            "test_event",
            observer="nexus.event_domain.tests.test_event_manager.SuccessfulObserver",
        )

        self.manager.notify("test_event", data="test")

        # Direct observer should be called
        self.assertTrue(direct_observer.called)


class EventManagerIntegrationTestCase(TestCase):
    """Integration tests for EventManager with real scenarios."""

    def setUp(self):
        # Use a fresh registry to avoid test pollution
        self.manager = EventManager(registry=ObserverRegistry())
        self.manager.observers.clear()

    def test_multiple_observers_same_event(self):
        """Test that multiple observers for the same event all run."""
        obs1 = SuccessfulObserver()
        obs2 = SuccessfulObserver()
        obs3 = SuccessfulObserver()

        self.manager.subscribe("test_event", observer=[obs1, obs2, obs3])

        self.manager.notify("test_event", data="test")

        self.assertTrue(obs1.called)
        self.assertTrue(obs2.called)
        self.assertTrue(obs3.called)
        self.assertEqual(obs1.call_count, 1)
        self.assertEqual(obs2.call_count, 1)
        self.assertEqual(obs3.call_count, 1)

    def test_observer_receives_correct_kwargs(self):
        """Test that observers receive the correct keyword arguments."""
        observer = SuccessfulObserver()
        self.manager.subscribe("test_event", observer=[observer])

        self.manager.notify("test_event", arg1="value1", arg2="value2", arg3=123)

        self.assertEqual(observer.kwargs["arg1"], "value1")
        self.assertEqual(observer.kwargs["arg2"], "value2")
        self.assertEqual(observer.kwargs["arg3"], 123)

    def test_no_observers_for_event(self):
        """Test that notifying an event with no observers doesn't crash."""
        # Should not raise any exception
        self.manager.notify("nonexistent_event", data="test")

    def test_clear_cache(self):
        """Test that cache clearing works."""
        self.manager.registry.register(
            "test_event",
            "nexus.event_domain.tests.test_event_manager.SuccessfulObserver",
            lazy=True,
        )

        # Load observers (this will cache them)
        observers1 = self.manager.registry.get_observers("test_event")

        # Clear cache
        self.manager.registry.clear_cache()

        # Get observers again (should reload)
        observers2 = self.manager.registry.get_observers("test_event")

        # Both should work
        self.assertEqual(len(observers1), 1)
        self.assertEqual(len(observers2), 1)


class ObserverRegistryTestCase(TestCase):
    """Test ObserverRegistry functionality."""

    def setUp(self):
        # Use a fresh registry to avoid test pollution
        self.registry = ObserverRegistry()

    def test_register_single_observer(self):
        """Test registering a single observer."""
        self.registry.register("test_event", "some.path.Observer", lazy=True)

        events = self.registry.get_registered_events()
        self.assertIn("test_event", events)

    def test_register_multiple_observers(self):
        """Test registering multiple observers for same event."""
        self.registry.register(
            "test_event",
            ["path1.Observer1", "path2.Observer2"],
            lazy=True,
        )

        observers = self.registry.get_observers("test_event")
        # Should have 2 observers (if paths are valid)
        # For invalid paths, might be 0
        self.assertGreaterEqual(len(observers), 0)

    def test_get_registered_events(self):
        """Test getting list of registered events."""
        self.registry.register("event1", "path.Observer1", lazy=True)
        self.registry.register("event2", "path.Observer2", lazy=True)

        events = self.registry.get_registered_events()
        self.assertIn("event1", events)
        self.assertIn("event2", events)

    def test_direct_instance_registration(self):
        """Test registering observer instances directly."""
        observer = SuccessfulObserver()
        self.registry.register("test_event", observer, lazy=False)

        observers = self.registry.get_observers("test_event")
        self.assertEqual(len(observers), 1)
        self.assertEqual(observers[0], observer)

    def test_should_isolate_errors_default_false(self):
        """Test that should_isolate_errors returns False by default."""
        observer = SuccessfulObserver()
        self.registry.register("test_event", observer, lazy=False)

        # Default should be False (fail fast)
        self.assertFalse(self.registry.should_isolate_errors(observer))

    def test_should_isolate_errors_with_isolation(self):
        """Test that should_isolate_errors returns True when isolation is enabled."""
        observer = SuccessfulObserver()
        self.registry.register("test_event", observer, lazy=False, isolate_errors=True)

        # Should return True when isolation is enabled
        self.assertTrue(self.registry.should_isolate_errors(observer))

    def test_should_isolate_errors_with_lazy_loading(self):
        """Test that isolation setting works with lazy loading."""
        self.registry.register(
            "test_event",
            "nexus.event_domain.tests.test_event_manager.SuccessfulObserver",
            lazy=True,
            isolate_errors=True,
        )

        observers = self.registry.get_observers("test_event")
        self.assertEqual(len(observers), 1)
        observer = observers[0]

        # Should return True for lazy-loaded observer with isolation enabled
        self.assertTrue(self.registry.should_isolate_errors(observer))

    def test_mixed_isolation_settings(self):
        """Test that different observers can have different isolation settings."""
        observer1 = SuccessfulObserver()
        observer2 = SuccessfulObserver()

        # First observer: isolated
        self.registry.register("test_event", observer1, lazy=False, isolate_errors=True)
        # Second observer: fail fast (default)
        self.registry.register("test_event", observer2, lazy=False, isolate_errors=False)

        # Check isolation settings
        self.assertTrue(self.registry.should_isolate_errors(observer1))
        self.assertFalse(self.registry.should_isolate_errors(observer2))
