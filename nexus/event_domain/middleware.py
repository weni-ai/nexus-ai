"""
Middleware system for observer execution hooks.

This module provides middleware for cross-cutting concerns like error tracking,
performance monitoring, and logging.
"""
import contextvars
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from django.conf import settings

logger = logging.getLogger(__name__)

# Context variable to store Sentry transaction for performance monitoring
# This allows us to track transactions across async boundaries
_sentry_transaction: contextvars.ContextVar[Optional[Any]] = contextvars.ContextVar('sentry_transaction', default=None)


class ObserverMiddleware(ABC):
    """
    Base class for observer middleware.

    Middleware can hook into observer execution to add cross-cutting concerns
    like error tracking, performance monitoring, or logging.
    """

    @abstractmethod
    def before_perform(self, observer, event: str, **kwargs) -> None:
        """
        Called before observer.perform() is executed.

        Args:
            observer: The observer instance
            event: The event name
            **kwargs: Event arguments
        """
        pass

    @abstractmethod
    def after_perform(self, observer, event: str, duration: float, **kwargs) -> None:
        """
        Called after observer.perform() completes successfully.

        Args:
            observer: The observer instance
            event: The event name
            duration: Execution time in seconds
            **kwargs: Event arguments
        """
        pass

    @abstractmethod
    def on_error(self, observer, event: str, error: Exception, duration: float, **kwargs) -> None:
        """
        Called when observer.perform() raises an exception.

        Args:
            observer: The observer instance
            event: The event name
            error: The exception that was raised
            duration: Execution time in seconds (before error)
            **kwargs: Event arguments
        """
        pass


class SentryErrorMiddleware(ObserverMiddleware):
    """
    Middleware that captures observer errors to Sentry.

    Automatically captures exceptions with context about the observer,
    event, and event arguments.
    """

    def __init__(self, enabled: bool = True):
        """
        Initialize Sentry error middleware.

        Args:
            enabled: Whether to capture errors to Sentry. Default True.
                    Can be disabled if USE_SENTRY is False.
        """
        self.enabled = enabled and getattr(settings, "USE_SENTRY", False)

    def before_perform(self, observer, event: str, **kwargs) -> None:
        """No action needed before perform."""
        pass

    def after_perform(self, observer, event: str, duration: float, **kwargs) -> None:
        """No action needed after successful perform."""
        pass

    def on_error(self, observer, event: str, error: Exception, duration: float, **kwargs) -> None:
        """Capture error to Sentry with context."""
        if not self.enabled:
            return

        try:
            import sentry_sdk

            observer_name = getattr(observer.__class__, "__name__", "Unknown")

            # Set tags for filtering in Sentry
            sentry_sdk.set_tag("observer", observer_name)
            sentry_sdk.set_tag("event", event)
            sentry_sdk.set_tag("observer_error", True)

            # Add context about the observer execution
            context = {
                "observer": observer_name,
                "event": event,
                "duration_seconds": duration,
                "kwargs": self._sanitize_kwargs(kwargs),
            }

            # Try to extract project_uuid if available
            project_uuid = kwargs.get("project_uuid") or kwargs.get("project")
            if project_uuid:
                sentry_sdk.set_tag("project_uuid", str(project_uuid))
                context["project_uuid"] = str(project_uuid)

            sentry_sdk.set_context("observer_execution", context)

            # Capture the exception
            sentry_sdk.capture_exception(error)

        except Exception as e:
            # Don't let Sentry middleware errors break the observer system
            logger.warning(f"Failed to capture error to Sentry: {e}", exc_info=True)

    def _sanitize_kwargs(self, kwargs: Dict[str, Any]) -> Dict[str, Any]:
        """
        Sanitize kwargs to avoid sending sensitive data to Sentry.

        Args:
            kwargs: Event arguments

        Returns:
            Sanitized kwargs dictionary
        """
        # Remove potentially large or sensitive data
        sanitized = {}
        skip_keys = {"trace_events", "inline_traces", "agent_response", "text", "message"}

        for key, value in kwargs.items():
            if key in skip_keys:
                sanitized[key] = f"<{type(value).__name__} (omitted)>"
            elif isinstance(value, (str, int, float, bool, type(None))):
                sanitized[key] = value
            elif isinstance(value, (list, dict)):
                # Include type and length, but not full content
                sanitized[key] = f"<{type(value).__name__} with {len(value)} items>"
            else:
                sanitized[key] = f"<{type(value).__name__}>"

        return sanitized


class PerformanceLoggingMiddleware(ObserverMiddleware):
    """
    Middleware that logs observer performance to Python logging.

    Logs execution time for observers to log files/console, with optional
    threshold warnings. Useful for local debugging and log analysis.

    Note: For production monitoring with dashboards and alerting, use
    SentryPerformanceMiddleware instead.
    """

    def __init__(self, enabled: bool = True, slow_threshold: float = 1.0):
        """
        Initialize performance monitoring middleware.

        Args:
            enabled: Whether to monitor performance. Default True.
            slow_threshold: Log warning if observer takes longer than this (seconds).
                           Default 1.0 second.
        """
        self.enabled = enabled
        self.slow_threshold = slow_threshold

    def before_perform(self, observer, event: str, **kwargs) -> None:
        """No action needed before perform."""
        pass

    def after_perform(self, observer, event: str, duration: float, **kwargs) -> None:
        """Log performance metrics."""
        if not self.enabled:
            return

        observer_name = getattr(observer.__class__, "__name__", "Unknown")

        if duration >= self.slow_threshold:
            logger.warning(
                f"Slow observer execution: '{observer_name}' for event '{event}' "
                f"took {duration:.3f}s (threshold: {self.slow_threshold}s)",
                extra={
                    "observer": observer_name,
                    "event": event,
                    "duration": duration,
                    "slow": True,
                },
            )
        else:
            logger.debug(
                f"Observer '{observer_name}' for event '{event}' took {duration:.3f}s",
                extra={
                    "observer": observer_name,
                    "event": event,
                    "duration": duration,
                },
            )

    def on_error(self, observer, event: str, error: Exception, duration: float, **kwargs) -> None:
        """Log performance even on error."""
        if not self.enabled:
            return

        observer_name = getattr(observer.__class__, "__name__", "Unknown")
        logger.debug(
            f"Observer '{observer_name}' for event '{event}' failed after {duration:.3f}s",
            extra={
                "observer": observer_name,
                "event": event,
                "duration": duration,
                "error": True,
            },
        )


class SentryPerformanceMiddleware(ObserverMiddleware):
    """
    Middleware that sends observer performance data to Sentry Performance Monitoring.

    Creates Sentry transactions/spans for observer execution, allowing you to
    track performance metrics in Sentry dashboards, set up alerts, and correlate
    errors with performance issues.

    This is the production-ready performance monitoring solution that integrates
    with Sentry's full performance monitoring features.
    """

    def __init__(self, enabled: bool = True, sample_rate: float = 1.0):
        """
        Initialize Sentry performance middleware.

        Args:
            enabled: Whether to send performance data to Sentry. Default True.
                    Can be disabled if USE_SENTRY is False.
            sample_rate: Rate at which to sample transactions (0.0 to 1.0).
                        Default 1.0 (100% sampling).
        """
        self.enabled = enabled and getattr(settings, 'USE_SENTRY', False)
        self.sample_rate = sample_rate

    def before_perform(self, observer, event: str, **kwargs) -> None:
        """Start Sentry transaction for observer execution."""
        if not self.enabled:
            return

        try:
            import sentry_sdk

            observer_name = getattr(observer.__class__, '__name__', 'Unknown')

            # Create transaction name
            transaction_name = f"observer.{observer_name}.{event}"

            # Start Sentry transaction
            transaction = sentry_sdk.start_transaction(
                name=transaction_name,
                op="observer.execute",
                sampled=self._should_sample(),
            )

            # Transaction might be None if not sampled or Sentry not initialized
            if not transaction:
                return

            # Set tags for filtering in Sentry
            transaction.set_tag("observer", observer_name)
            transaction.set_tag("event", event)
            transaction.set_tag("observer_performance", True)

            # Try to extract project_uuid if available
            project_uuid = kwargs.get('project_uuid')
            if not project_uuid and kwargs.get('project'):
                project = kwargs.get('project')
                if hasattr(project, 'uuid'):
                    project_uuid = str(project.uuid)
            if project_uuid:
                transaction.set_tag("project_uuid", str(project_uuid))

            # Store transaction in context variable for later retrieval
            _sentry_transaction.set(transaction)

        except Exception as e:
            # Don't let Sentry middleware errors break the observer system
            logger.warning(f"Failed to start Sentry transaction: {e}", exc_info=True)

    def after_perform(self, observer, event: str, duration: float, **kwargs) -> None:
        """Finish Sentry transaction with success status."""
        if not self.enabled:
            return

        try:
            transaction = _sentry_transaction.get()
            if transaction:
                # Set duration measurement
                transaction.set_measurement("duration", duration, unit="second")

                # Set status to success
                transaction.set_status("ok")

                # Finish transaction
                transaction.finish()

                # Clear context variable
                _sentry_transaction.set(None)

        except Exception as e:
            # Don't let Sentry middleware errors break the observer system
            logger.warning(f"Failed to finish Sentry transaction: {e}", exc_info=True)

    def on_error(self, observer, event: str, error: Exception, duration: float, **kwargs) -> None:
        """Finish Sentry transaction with error status."""
        if not self.enabled:
            return

        try:
            transaction = _sentry_transaction.get()
            if transaction:
                # Set duration measurement
                transaction.set_measurement("duration", duration, unit="second")

                # Set status to error
                transaction.set_status("internal_error")

                # Add error context
                transaction.set_data("error_type", type(error).__name__)
                transaction.set_data("error_message", str(error))

                # Finish transaction
                transaction.finish()

                # Clear context variable
                _sentry_transaction.set(None)

        except Exception as e:
            # Don't let Sentry middleware errors break the observer system
            logger.warning(f"Failed to finish Sentry transaction on error: {e}", exc_info=True)

    def _should_sample(self) -> bool:
        """Determine if transaction should be sampled."""
        import random
        return random.random() < self.sample_rate


class MiddlewareChain:
    """
    Chain of middleware to execute in order.

    Manages the execution of multiple middleware hooks.
    """

    def __init__(self, middlewares: Optional[list] = None):
        """
        Initialize middleware chain.

        Args:
            middlewares: List of ObserverMiddleware instances
        """
        self.middlewares = middlewares or []

    def add(self, middleware: ObserverMiddleware) -> None:
        """Add middleware to the chain."""
        self.middlewares.append(middleware)

    def before_perform(self, observer, event: str, **kwargs) -> None:
        """Execute all before_perform hooks."""
        for middleware in self.middlewares:
            try:
                middleware.before_perform(observer, event, **kwargs)
            except Exception as e:
                logger.warning(f"Middleware {middleware.__class__.__name__} before_perform failed: {e}")

    def after_perform(self, observer, event: str, duration: float, **kwargs) -> None:
        """Execute all after_perform hooks."""
        for middleware in self.middlewares:
            try:
                middleware.after_perform(observer, event, duration, **kwargs)
            except Exception as e:
                logger.warning(f"Middleware {middleware.__class__.__name__} after_perform failed: {e}")

    def on_error(self, observer, event: str, error: Exception, duration: float, **kwargs) -> None:
        """Execute all on_error hooks."""
        for middleware in self.middlewares:
            try:
                middleware.on_error(observer, event, error, duration, **kwargs)
            except Exception as e:
                logger.warning(f"Middleware {middleware.__class__.__name__} on_error failed: {e}")


def create_default_middleware_chain() -> MiddlewareChain:
    """
    Create default middleware chain with Sentry and performance monitoring.

    Returns:
        MiddlewareChain with default middleware configured
    """
    chain = MiddlewareChain()

    # Add Sentry error tracking
    chain.add(SentryErrorMiddleware())

    # Add Sentry performance monitoring (sends to Sentry dashboards)
    chain.add(SentryPerformanceMiddleware())

    # Add performance logging (logs to Python logging)
    chain.add(PerformanceLoggingMiddleware())

    return chain
