# Observer Architecture Guide

## Overview

The observer pattern allows decoupled event-driven communication. When an event occurs, all registered observers are automatically notified. This guide explains how to use the observer system in the Nexus AI codebase.

## Quick Start

### Creating an Observer

```python
from nexus.event_domain.decorators import observer
from nexus.event_domain.event_observer import EventObserver

@observer("my_event")
class MyObserver(EventObserver):
    def perform(self, **kwargs):
        # Access event data from kwargs
        data = kwargs.get("data")
        # Your logic here
        pass
```

### Triggering Events

```python
from nexus.events import event_manager

event_manager.notify(
    event="my_event",
    data={"key": "value"},
    other_param=123
)
```

**Important:** For the observer to be registered, its module must be listed in `nexus/observers/apps.py`:

```python
# nexus/observers/apps.py
OBSERVER_MODULES = [
    # ... existing modules ...
    "your_app.observers",  # Add your module here
]
```

## Core Concepts

### EventManager

The `EventManager` is the central component that:
- Registers observers for events
- Notifies observers when events occur
- Handles error isolation and middleware

```python
from nexus.events import event_manager, async_event_manager

# Synchronous events
event_manager.notify("event_name", **kwargs)

# Asynchronous events
await async_event_manager.notify("event_name", **kwargs)

# Call async observers from sync code (non-blocking)
from nexus.events import notify_async
notify_async("event_name", **kwargs)  # Runs in background thread
```

### notify_async Helper

Use `notify_async()` to call async observers from synchronous code (e.g., Django views, Celery tasks):

```python
from nexus.events import notify_async

# In a Django view or Celery task
def my_sync_function():
    # This won't block - runs async observers in background thread
    notify_async("cache_invalidation:project", project_uuid=str(project.uuid))
```

### EventObserver

All observers must inherit from `EventObserver` and implement the `perform()` method:

```python
from nexus.event_domain.event_observer import EventObserver

class MyObserver(EventObserver):
    def perform(self, **kwargs):
        # Observer logic
        pass
```

## Features

### 1. Decorator-Based Registration

**When to use:** Always. This is the simplest and recommended way to register observers.

**How it works:**
1. Use the `@observer` decorator on your observer class
2. Add your module to `OBSERVER_MODULES` in `nexus/observers/apps.py`
3. Observers are automatically registered at Django startup via `AppConfig.ready()`

**Why this approach:**
- Avoids circular import issues (registration happens after all apps load)
- Centralized list of all observer modules
- Graceful error handling (one failing module doesn't break others)

**Example:**
```python
@observer("intelligence_create_activity")
class IntelligenceCreateObserver(EventObserver):
    def perform(self, intelligence):
        # Process intelligence creation
        pass
```

**Options:**
```python
# With error isolation (non-critical observer)
@observer("health_check", isolate_errors=True)
class HealthCheckObserver(EventObserver):
    pass

# With dependency injection factory
@observer("inline_trace_observers", factory=create_rationale_observer)
class RationaleObserver(EventObserver):
    pass

# Async observer
@observer("async_event", manager="async")
class AsyncObserver(EventObserver):
    async def perform(self, **kwargs):
        await some_async_operation()

# Register to both sync and async managers
@observer("save_events", manager=["sync", "async"])
class SaveObserver(EventObserver):
    pass
```

### 2. Error Isolation

**When to use:**
- **Fail-Fast (Default)**: For critical observers that must succeed (data validation, critical business logic)
- **Isolated**: For non-critical observers (logging, metrics, notifications, external API calls)

**How it works:**
- **Fail-Fast**: If observer fails, exception propagates and execution stops
- **Isolated**: If observer fails, error is logged and execution continues

**Example:**
```python
# Critical observer - fail fast (default)
@observer("order_created")
class ValidateOrderObserver(EventObserver):
    def perform(self, order):
        # If this fails, everything stops
        validate_order(order)

# Non-critical observer - isolated
@observer("order_created", isolate_errors=True)
class TrackOrderObserver(EventObserver):
    def perform(self, order):
        # If this fails, other observers still run
        analytics.track(order)
```

**Decision Guide:**
- Use **fail-fast** when: Data integrity is critical, transaction requirements, validation logic
- Use **isolated** when: Logging, metrics, notifications, external services that might fail

### 3. Dependency Injection (Factory Pattern)

**When to use:** When your observer needs dependencies (clients, services, configuration).

**Why use it:**
- Makes testing easier (can mock dependencies)
- Centralizes dependency creation
- Avoids circular imports

**How it works:**
1. Create a factory function that instantiates the observer with dependencies
2. Pass the factory to the `@observer` decorator
3. Factory is called when observer is instantiated

**Example:**
```python
# Factory function
def create_rationale_observer(observer_class):
    from nexus.usecases.inline_agents.typing import TypingUsecase
    import boto3

    bedrock_client = boto3.client("bedrock-runtime", ...)
    typing_usecase = TypingUsecase()

    return observer_class(
        bedrock_client=bedrock_client,
        typing_usecase=typing_usecase,
        model_id=settings.AWS_RATIONALE_MODEL
    )

# Register with factory
@observer("inline_trace_observers", factory=create_rationale_observer)
class RationaleObserver(EventObserver):
    def __init__(self, bedrock_client, typing_usecase, model_id):
        self.bedrock_client = bedrock_client
        self.typing_usecase = typing_usecase
        self.model_id = model_id

    def perform(self, **kwargs):
        # Use dependencies
        pass
```

**Best Practice:** Use lazy imports in factories to avoid circular dependencies.

### 4. Middleware

**When to use:** For cross-cutting concerns like error tracking, performance monitoring, logging.

**What's included:**
- **SentryErrorMiddleware**: Automatically captures all observer errors to Sentry
- **PerformanceMonitoringMiddleware**: Logs execution time and warns on slow observers

**How it works:**
- Middleware hooks are automatically called:
  - `before_perform()`: Before observer execution
  - `after_perform()`: After successful execution (with duration)
  - `on_error()`: When an error occurs (with duration)

**Custom Middleware Example:**
```python
from nexus.event_domain.middleware import ObserverMiddleware

class CustomMiddleware(ObserverMiddleware):
    def before_perform(self, observer, event: str, **kwargs):
        logger.info(f"Executing {observer.__class__.__name__} for {event}")

    def after_perform(self, observer, event: str, duration: float, **kwargs):
        if duration > 1.0:
            logger.warning(f"Slow observer: {observer.__class__.__name__} took {duration:.2f}s")

    def on_error(self, observer, event: str, error: Exception, duration: float, **kwargs):
        # Error already captured by Sentry middleware
        pass
```

**Using Custom Middleware:**
```python
from nexus.event_domain.middleware import MiddlewareChain, SentryErrorMiddleware, PerformanceMonitoringMiddleware

# Create custom middleware chain
chain = MiddlewareChain()
chain.add(SentryErrorMiddleware())
chain.add(PerformanceMonitoringMiddleware(slow_threshold=2.0))
chain.add(CustomMiddleware())

# Create manager with custom middleware
from nexus.event_domain.event_manager import EventManager
manager = EventManager(middleware=chain)
```

### 5. Event Validation

**When to use:** To ensure event payloads have required fields and correct types before observers run.

**How it works:**
- Validators check payload structure and types
- Validation happens before any observer runs
- Invalid payloads raise exceptions immediately

**Example:**
```python
from nexus.event_domain.validators import RequiredFieldsValidator, FieldTypeValidator, ValidatorChain

# Create validator chain
chain = ValidatorChain()
chain.add(RequiredFieldsValidator(["project_uuid", "user_id"]))
chain.add(FieldTypeValidator({"project_uuid": str, "count": int}))

# Add to event manager
from nexus.events import event_manager
event_manager.add_validator("test_event", chain)

# Valid - passes
event_manager.notify("test_event", project_uuid="123", user_id="456", count=5)

# Invalid - raises ValueError (missing user_id)
event_manager.notify("test_event", project_uuid="123", count=5)
```

**Built-in Validators:**
- `RequiredFieldsValidator`: Ensures required fields are present
- `FieldTypeValidator`: Ensures fields have correct types
- `CompositeValidator`: Combines multiple validators

**Custom Validator Example:**
```python
from nexus.event_domain.validators import EventValidator, ValidatorChain

class CustomValidator(EventValidator):
    def validate(self, event: str, payload: dict):
        if "custom_field" not in payload:
            raise ValueError("custom_field is required")
        if payload["custom_field"] != "expected_value":
            raise ValueError("custom_field must be 'expected_value'")

chain = ValidatorChain()
chain.add(CustomValidator())
event_manager.add_validator("test_event", chain)
```

## Usage Patterns

### Synchronous Observer

```python
@observer("intelligence_create_activity")
class IntelligenceCreateObserver(EventObserver):
    def perform(self, intelligence):
        # Synchronous logic
        process_intelligence(intelligence)
```

### Asynchronous Observer

```python
@observer("async_event", manager="async")
class AsyncObserver(EventObserver):
    async def perform(self, **kwargs):
        # Async logic
        await some_async_operation()
```

### Multiple Observers for Same Event

```python
@observer("order_created")
class ValidateOrderObserver(EventObserver):
    def perform(self, order):
        validate_order(order)

@observer("order_created", isolate_errors=True)
class TrackOrderObserver(EventObserver):
    def perform(self, order):
        analytics.track(order)

@observer("order_created", isolate_errors=True)
class SendNotificationObserver(EventObserver):
    def perform(self, order):
        send_email(order)
```

All three observers will be called when `order_created` event is triggered.

### Observer with Dependencies

```python
def create_my_observer(observer_class):
    from some.module import Dependency
    dependency = Dependency()
    return observer_class(dependency=dependency)

@observer("my_event", factory=create_my_observer)
class MyObserver(EventObserver):
    def __init__(self, dependency):
        self.dependency = dependency

    def perform(self, **kwargs):
        self.dependency.do_something()
```

## Testing

### Running Tests

```bash
# All event domain tests
python manage.py test nexus.event_domain.tests

# Specific test class
python manage.py test nexus.event_domain.tests.test_event_manager.ErrorIsolationTestCase

# Verbose output
python manage.py test nexus.event_domain.tests --verbosity=2
```

### Testing Your Observer

```python
from django.test import TestCase
from nexus.events import event_manager

class MyObserverTest(TestCase):
    def test_observer_execution(self):
        # Create test data
        test_data = {"key": "value"}

        # Trigger event
        event_manager.notify("my_event", data=test_data)

        # Assert expected behavior
        # ...
```

### Testing with Mocked Dependencies

```python
from unittest.mock import Mock, patch

def test_observer_with_mocked_dependency():
    # Mock the dependency
    mock_dependency = Mock()

    # Create factory that uses mock
    def create_observer(observer_class):
        return observer_class(dependency=mock_dependency)

    # Test observer
    observer = create_observer(MyObserver)
    observer.perform(data="test")

    # Assert mock was called
    mock_dependency.do_something.assert_called_once()
```

## File Structure

```
nexus/
├── events.py                  # Event managers and notify_async helper
├── observers/                 # Observer registration app
│   ├── __init__.py
│   └── apps.py               # OBSERVER_MODULES list and AppConfig.ready()
└── event_domain/
    ├── event_observer.py      # Base EventObserver class
    ├── event_manager.py       # EventManager and AsyncEventManager
    ├── observer_registry.py   # Lazy loading registry
    ├── observer_factories.py  # Factory functions
    ├── decorators.py          # @observer decorator
    ├── middleware.py          # Middleware system
    ├── validators.py          # Event validation
    └── tests/
        └── test_event_manager.py  # Comprehensive tests
```

**Observer Implementations (examples):**
```
router/
├── tasks/workflow_observers.py           # Typing indicator observer
├── services/cache_invalidation_observers.py  # Cache invalidation
└── traces_observers/
    ├── rationale/observer.py             # Rationale observer
    ├── save_traces.py                    # Save traces observer
    └── summary.py                        # Summary observer

nexus/
├── intelligences/observer.py             # Intelligence activity observer
├── projects/observer.py                  # Project activity observer
├── actions/observers.py                  # Actions observer
└── logs/observers.py                     # Logs observer
```

## Adding a New Observer

### Step 1: Create the Observer

```python
# your_app/observers.py
from nexus.event_domain.decorators import observer
from nexus.event_domain.event_observer import EventObserver

@observer("your_event_name", isolate_errors=True)
class YourObserver(EventObserver):
    def perform(self, **kwargs):
        # Your logic here
        pass
```

### Step 2: Register the Module

Add your module to `OBSERVER_MODULES` in `nexus/observers/apps.py`:

```python
# nexus/observers/apps.py
OBSERVER_MODULES = [
    # ... existing modules ...
    "your_app.observers",  # Add this line
]
```

### Step 3: Trigger the Event

```python
from nexus.events import event_manager, notify_async

# Synchronous
event_manager.notify("your_event_name", data={"key": "value"})

# Async observers from sync code
notify_async("your_event_name", data={"key": "value"})
```

---

## Best Practices

1. **Use Decorator Registration**: Always use `@observer` decorator - it's the simplest approach
2. **Register Your Module**: Add your observer module to `nexus/observers/apps.py`
3. **Fail-Fast for Critical Logic**: Use default behavior (fail-fast) for data validation and critical business logic
4. **Isolate Non-Critical Observers**: Use `isolate_errors=True` for logging, metrics, and notifications
5. **Use `notify_async` for Async Observers**: When calling async observers from sync code (Django views, Celery tasks)
6. **Use Factories for Dependencies**: Makes testing easier and avoids circular imports
7. **Validate Event Payloads**: Use validators to catch errors early and document expected structure
8. **Monitor Isolated Errors**: Check logs regularly for failures in isolated observers
9. **Keep Observers Focused**: Each observer should do one thing well
10. **Use Type Hints**: Helps document expected payload structure

## Common Patterns

### Pattern: Critical Validation + Non-Critical Side Effects

```python
# Critical - must succeed
@observer("order_created")
class ValidateOrderObserver(EventObserver):
    def perform(self, order):
        if not order.is_valid():
            raise ValueError("Invalid order")

# Non-critical - can fail
@observer("order_created", isolate_errors=True)
class LogOrderObserver(EventObserver):
    def perform(self, order):
        logger.info(f"Order created: {order.id}")

@observer("order_created", isolate_errors=True)
class TrackOrderObserver(EventObserver):
    def perform(self, order):
        analytics.track("order_created", order.id)
```

### Pattern: Observer with External Service

```python
@observer("send_notification", isolate_errors=True)
class EmailNotificationObserver(EventObserver):
    def perform(self, user_email, message):
        # External service might fail - isolate errors
        email_service.send(user_email, message)
```

### Pattern: Observer with Complex Dependencies

```python
def create_complex_observer(observer_class):
    # Lazy imports to avoid circular dependencies
    from module1 import Service1
    from module2 import Service2

    service1 = Service1()
    service2 = Service2()

    return observer_class(service1=service1, service2=service2)

@observer("complex_event", factory=create_complex_observer)
class ComplexObserver(EventObserver):
    def __init__(self, service1, service2):
        self.service1 = service1
        self.service2 = service2

    def perform(self, **kwargs):
        result = self.service1.process(kwargs)
        self.service2.save(result)
```

## Future Possible Implementations

The following features could be added in the future if needed:

### Observer Priority/Ordering

Control the execution order of observers:

```python
@observer("order_created", priority=ObserverPriority.HIGH)
class ValidateOrderObserver(EventObserver):
    pass

@observer("order_created", priority=ObserverPriority.NORMAL)
class ProcessOrderObserver(EventObserver):
    pass
```

**Status:** Not implemented. Current execution order is registration order.

### Event Context

Provide structured event data with metadata:

```python
@dataclass
class EventContext:
    event_name: str
    timestamp: float
    payload: Dict[str, Any]
    metadata: Dict[str, Any]
```

**Status:** Not implemented. Current system uses plain kwargs.

### Unsubscribe Capability

Allow dynamic registration/unregistration:

```python
event_manager.unsubscribe("my_event", "module.Observer")
event_manager.disable("my_event", "module.Observer")
event_manager.enable("my_event", "module.Observer")
```

**Status:** Not implemented. Observers are registered at startup.

### Observer Metadata

Store rich information about observers:

```python
@observer("my_event", description="Processes user data", version="1.0")
class MyObserver(EventObserver):
    pass
```

**Status:** Not implemented. Basic registration info is stored but not exposed.
