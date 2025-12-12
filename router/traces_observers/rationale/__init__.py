"""
Rationale observer package.

This package contains all components related to rationale processing:
- observer: Main RationaleObserver class
- context: Context and trace data classes
- handlers: Handler classes for different processing scenarios
"""

from router.traces_observers.rationale.observer import RationaleObserver

__all__ = ["RationaleObserver"]
