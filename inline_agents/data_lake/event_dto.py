from dataclasses import dataclass, field
from typing import Any, Dict


@dataclass
class DataLakeEventDTO:
    """DTO for validating data lake events before sending."""

    event_name: str
    date: str
    project: str
    contact_urn: str
    key: str
    value_type: str
    value: Any
    metadata: Dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate field content (empty/whitespace strings, None values, event_name)."""
        errors = []

        # Fields that cannot be empty or whitespace-only
        string_fields = {
            "project": self.project,
            "contact_urn": self.contact_urn,
            "key": self.key,
            "date": self.date,
            "value_type": self.value_type,
        }

        for field_name, field_value in string_fields.items():
            if not field_value or not str(field_value).strip():
                errors.append(f"{field_name} cannot be empty")

        # Value cannot be None
        if self.value is None:
            errors.append("value cannot be None")

        # Event name must be specific value
        if self.event_name != "weni_nexus_data":
            errors.append('event_name must be "weni_nexus_data"')

        if errors:
            raise ValueError(f"Event validation failed: {', '.join(errors)}")

    def dict(self) -> Dict[str, Any]:
        """Convert DTO to dictionary for sending to data lake."""
        return {
            "event_name": self.event_name,
            "date": self.date,
            "project": self.project.strip() if self.project else "",
            "contact_urn": self.contact_urn.strip() if self.contact_urn else "",
            "key": self.key.strip() if self.key else "",
            "value_type": self.value_type,
            "value": self.value,
            "metadata": self.metadata,
        }
