from dataclasses import dataclass


@dataclass
class ProjectCreationDTO:
    uuid: str
    name: str
    org_uuid: str
    template_type_uuid: str
    is_template: bool
    brain_on: bool


@dataclass
class TriggerConsumerDTO:
    action: str
    entity: str
    entity_name: str
    user_email: str
    flow_organization: str
    entity_uuid: str
    project_uuid: str
