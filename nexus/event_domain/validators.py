"""
Event validation system for observer pattern.

This module provides validators to ensure event payloads meet expected requirements
before observers are notified.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class EventValidator(ABC):
    """
    Abstract base class for event payload validators.

    Validators are called before observers are notified to ensure
    the event payload meets expected requirements.
    """

    @abstractmethod
    def validate(self, event: str, payload: Dict[str, Any]) -> None:
        """
        Validate event payload.

        Args:
            event: The event name
            payload: The event payload (kwargs)

        Raises:
            ValueError: If validation fails
            TypeError: If payload type is incorrect
            Any other exception: If validation fails

        Returns:
            None if validation passes
        """
        pass


class RequiredFieldsValidator(EventValidator):
    """
    Validator that ensures required fields are present in the payload.

    Example:
        validator = RequiredFieldsValidator(["project_uuid", "user_id"])
        validator.validate("test_event", {"project_uuid": "123", "user_id": "456"})  # OK
        validator.validate("test_event", {"project_uuid": "123"})  # Raises ValueError
    """

    def __init__(self, required_fields: List[str]):
        """
        Initialize validator with required fields.

        Args:
            required_fields: List of field names that must be present in payload
        """
        self.required_fields = required_fields

    def validate(self, event: str, payload: Dict[str, Any]) -> None:
        """Validate that all required fields are present."""
        missing_fields = [field for field in self.required_fields if field not in payload]
        if missing_fields:
            raise ValueError(f"Event '{event}' missing required fields: {', '.join(missing_fields)}")


class FieldTypeValidator(EventValidator):
    """
    Validator that ensures fields have correct types.

    Example:
        validator = FieldTypeValidator({"project_uuid": str, "count": int})
        validator.validate("test_event", {"project_uuid": "123", "count": 5})  # OK
        validator.validate("test_event", {"project_uuid": 123})  # Raises TypeError
    """

    def __init__(self, field_types: Dict[str, type]):
        """
        Initialize validator with expected field types.

        Args:
            field_types: Dictionary mapping field names to expected types
        """
        self.field_types = field_types

    def validate(self, event: str, payload: Dict[str, Any]) -> None:
        """Validate that fields have correct types."""
        for field_name, expected_type in self.field_types.items():
            if field_name in payload:
                value = payload[field_name]
                if not isinstance(value, expected_type):
                    raise TypeError(
                        f"Event '{event}' field '{field_name}' must be of type "
                        f"{expected_type.__name__}, got {type(value).__name__}"
                    )


class CompositeValidator(EventValidator):
    """
    Validator that combines multiple validators.

    All validators must pass for validation to succeed.

    Example:
        validator = CompositeValidator([
            RequiredFieldsValidator(["project_uuid"]),
            FieldTypeValidator({"project_uuid": str})
        ])
    """

    def __init__(self, validators: List[EventValidator]):
        """
        Initialize composite validator.

        Args:
            validators: List of validators to run in sequence
        """
        self.validators = validators

    def validate(self, event: str, payload: Dict[str, Any]) -> None:
        """Run all validators in sequence."""
        for validator in self.validators:
            validator.validate(event, payload)


class ValidatorChain:
    """
    Chain of validators for an event.

    Manages multiple validators and executes them in order.
    """

    def __init__(self, validators: Optional[List[EventValidator]] = None):
        """
        Initialize validator chain.

        Args:
            validators: List of EventValidator instances
        """
        self.validators = validators or []

    def add(self, validator: EventValidator) -> None:
        """Add validator to the chain."""
        self.validators.append(validator)

    def validate(self, event: str, payload: Dict[str, Any]) -> None:
        """
        Validate event payload using all validators in the chain.

        Args:
            event: The event name
            payload: The event payload

        Raises:
            Exception: If any validator fails
        """
        for validator in self.validators:
            try:
                validator.validate(event, payload)
            except Exception as e:
                logger.warning(
                    f"Event '{event}' validation failed: {e}",
                    extra={"event": event, "payload_keys": list(payload.keys())},
                )
                raise
