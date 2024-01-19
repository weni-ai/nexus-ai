from dataclasses import dataclass


@dataclass
class ProjectCreationDTO:
    uuid: str
    name: str
    org_uuid: str
    template_type_uuid: str
    is_template: bool
